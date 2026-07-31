"""The pipeline stages, split at the seams the original single
`run_analysis_pipeline` function already had. Each stage takes only
`(repository_id, settings)` and opens its own `SessionLocal()` -- no state
passes between stages in-memory, so every stage is already safe behind a
future queue boundary with zero changes. The one place this would otherwise
matter (SCANNING producing chunks that EMBEDDING needs) is resolved by
EMBEDDING re-deriving chunks itself via `TreeSitterParser.parse()` rather
than receiving them -- cheap, deterministic, local CPU, so paying for it
twice is a non-issue and keeps the stage boundary real today instead of a
"fix later" gap.

Note on SCANNING vs KNOWLEDGE_BUILT: detector-running and knowledge assembly
are one atomic, in-process unit of work in this codebase (no LLM streaming
or checkpointing between them) -- splitting them into two separate StageDefs
would mean re-running every detector twice just to get a status flicker.
Instead, `run_scanning_and_knowledge_stage` is registered under the
SCANNING StageDef (so it's the visible status for however long detectors +
tree-sitter + the LLM enrichment call take) and makes one extra direct
status update to KNOWLEDGE_BUILT right before returning, once persistence
has actually happened -- so both statuses are still real, observed
transitions, just backed by a single pass of work.
"""

import logging
import os
import shutil
import stat
import uuid
from pathlib import Path

import git
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.ai.embeddings.factory import get_embeddings
from app.ai.llm.factory import get_chat_model
from app.ai.vectorstore.qdrant_store import ensure_collection, get_qdrant_client, get_vectorstore
from app.core.config import Settings
from app.database.session import SessionLocal
from app.models.orm.repository import Repository
from app.models.schemas.repository import RepositoryStatus
from app.services.knowledge_builder.persistence import persist_knowledge
from app.services.repository.clone.github_cloner import GithubCloner
from app.services.repository.clone.zip_extractor import ZipExtractor
from app.services.repository.parser.chunk_builder import CodeChunk
from app.services.repository.parser.tree_sitter_parser import TreeSitterParser
from app.services.repository.pipeline.types import StageDef
from app.services.repository.scanner import RepositoryScanner
from app.utils.file_utils import ensure_dir

logger = logging.getLogger(__name__)


def _clear_readonly_and_retry(func, path, exc_info) -> None:
    """shutil.rmtree onerror handler: git marks pack files read-only, which
    raises PermissionError on Windows unless cleared before retrying the
    delete. Only handles PermissionError specifically -- anything else
    re-raises as-is rather than silently retrying into a more confusing
    failure."""
    if not isinstance(exc_info[1], PermissionError):
        raise exc_info[1]
    os.chmod(path, stat.S_IWRITE)
    func(path)


def run_cloning_stage(repository_id: uuid.UUID, settings: Settings) -> None:
    db = SessionLocal()
    try:
        repository = db.get(Repository, repository_id)
        if repository is None:
            raise RuntimeError(f"repository {repository_id} not found")

        ensure_dir(settings.repositories_dir)
        dest = Path(settings.repositories_dir) / str(repository_id)
        if dest.exists():
            # Re-analysis: clone_from()/extractall() both refuse to write into an
            # already-populated directory, so start from a clean slate.
            shutil.rmtree(dest, onerror=_clear_readonly_and_retry)

        if repository.source_url:
            repo_path = GithubCloner.from_settings(settings).clone(repository.source_url, dest)
            try:
                repository.last_analyzed_commit_sha = git.Repo(repo_path).head.commit.hexsha
            except Exception:
                logger.warning(
                    "could not read HEAD commit sha for %s", repository_id, exc_info=True
                )
        else:
            repo_path = ZipExtractor().clone(repository.local_path, dest)

        repository.local_path = str(repo_path)
        db.commit()
    finally:
        db.close()


def run_scanning_and_knowledge_stage(repository_id: uuid.UUID, settings: Settings) -> None:
    db = SessionLocal()
    try:
        repository = db.get(Repository, repository_id)
        if repository is None or repository.local_path is None:
            raise RuntimeError(f"repository {repository_id} has no local_path to scan")
        repo_path = Path(repository.local_path)

        chat_model = None
        try:
            chat_model = get_chat_model(settings)
        except Exception:
            logger.warning(
                "Could not build a chat model for knowledge enrichment; continuing without it",
                exc_info=True,
            )

        knowledge, _chunks = RepositoryScanner(chat_model=chat_model).scan(repository_id, repo_path)
        persist_knowledge(db, repository_id, knowledge)

        repository.status = RepositoryStatus.KNOWLEDGE_BUILT.value
        db.commit()
    finally:
        db.close()


def run_embedding_stage(repository_id: uuid.UUID, settings: Settings) -> None:
    db = SessionLocal()
    try:
        repository = db.get(Repository, repository_id)
        if repository is None or repository.local_path is None:
            raise RuntimeError(f"repository {repository_id} has no local_path to embed")
        repo_path = Path(repository.local_path)
    finally:
        db.close()

    chunks = TreeSitterParser().parse(repo_path)
    if not chunks:
        return
    _embed_chunks(settings, repository_id, chunks)


def _delete_stale_chunks(settings: Settings, repository_id: uuid.UUID, current_run_id: str) -> None:
    """Clear this repository's chunks from PRIOR runs (matching repository_id
    but NOT this run's run_id) -- called only after the new chunks are already
    written, so a failed embed never leaves a repository with zero retrievable
    chunks when it previously had working ones."""
    client = get_qdrant_client()
    try:
        client.get_collection(settings.qdrant_collection_name)
    except (UnexpectedResponse, ValueError):
        return  # collection doesn't exist yet -- nothing to clear
    client.delete(
        collection_name=settings.qdrant_collection_name,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="metadata.repository_id", match=MatchValue(value=str(repository_id))
                )
            ],
            must_not=[FieldCondition(key="metadata.run_id", match=MatchValue(value=current_run_id))],
        ),
    )


def _embed_chunks(settings: Settings, repository_id: uuid.UUID, chunks: list[CodeChunk]) -> None:
    embeddings = get_embeddings(settings)
    # Probe once to learn the provider's vector size rather than hardcoding it.
    vector_size = len(embeddings.embed_query(chunks[0].content[:200]))
    ensure_collection(get_qdrant_client(), settings, vector_size)

    # Tag every point from this run so stale points from a PRIOR run of the same
    # repository can be told apart and swept up once these new ones are confirmed
    # written -- add-then-delete, not delete-then-add, so a failure here leaves
    # the repository's previous (still working) chunks in place instead of none.
    run_id = str(uuid.uuid4())
    vectorstore = get_vectorstore(settings, embeddings)
    texts = [chunk.content for chunk in chunks]
    metadatas = [
        {
            "repository_id": str(repository_id),
            "run_id": run_id,
            "file_path": chunk.file_path,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "language": chunk.language,
            "symbol_name": chunk.symbol_name,
        }
        for chunk in chunks
    ]
    vectorstore.add_texts(texts, metadatas=metadatas)

    _delete_stale_chunks(settings, repository_id, run_id)


PIPELINE: list[StageDef] = [
    StageDef(RepositoryStatus.CLONING, run_cloning_stage),
    StageDef(RepositoryStatus.SCANNING, run_scanning_and_knowledge_stage),
    StageDef(RepositoryStatus.EMBEDDING, run_embedding_stage),
]
