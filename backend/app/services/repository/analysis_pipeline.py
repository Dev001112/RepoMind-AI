"""Orchestrates one full repository analysis run: clone/extract -> scan ->
embed -> persist -> status transitions.

Runs as a FastAPI BackgroundTask, so it owns its own DB session -- the
request's session dependency is already closed by the time this executes.
"""

import logging
import os
import shutil
import stat
import uuid
from pathlib import Path

from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.ai.embeddings.factory import get_embeddings
from app.ai.llm.factory import get_chat_model
from app.ai.vectorstore.qdrant_store import ensure_collection, get_qdrant_client, get_vectorstore
from app.core.config import Settings, get_settings
from app.database.session import SessionLocal
from app.models.orm.knowledge import RepositoryKnowledge as RepositoryKnowledgeORM
from app.models.orm.repository import Repository
from app.services.repository.clone.github_cloner import GithubCloner
from app.services.repository.clone.zip_extractor import ZipExtractor
from app.services.repository.parser.chunk_builder import CodeChunk
from app.services.repository.scanner import RepositoryScanner
from app.utils.file_utils import ensure_dir

logger = logging.getLogger(__name__)


def _clear_readonly_and_retry(func, path, exc_info) -> None:
    """shutil.rmtree onerror handler: git marks pack files read-only, which
    raises PermissionError on Windows unless cleared before retrying the
    delete. ignore_errors=True would silently leave those files (and the
    whole non-empty directory) behind instead -- which then makes the
    following git clone fail because the destination isn't actually empty.

    Only handles PermissionError specifically -- anything else (a vanished
    path, a file locked by another process) re-raises as-is rather than
    silently retrying into a more confusing failure."""
    if not isinstance(exc_info[1], PermissionError):
        raise exc_info[1]
    os.chmod(path, stat.S_IWRITE)
    func(path)


def run_analysis_pipeline(repository_id: uuid.UUID) -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        repository = db.get(Repository, repository_id)
        if repository is None:
            logger.warning("run_analysis_pipeline: repository %s not found", repository_id)
            return

        repository.status = "cloning"
        db.commit()

        ensure_dir(settings.repositories_dir)
        dest = Path(settings.repositories_dir) / str(repository_id)
        if dest.exists():
            # Re-analysis: clone_from()/extractall() both refuse to write into an
            # already-populated directory, so start from a clean slate.
            shutil.rmtree(dest, onerror=_clear_readonly_and_retry)

        if repository.source_url:
            repo_path = GithubCloner.from_settings(settings).clone(repository.source_url, dest)
        else:
            repo_path = ZipExtractor().clone(repository.local_path, dest)

        repository.local_path = str(repo_path)
        repository.status = "analyzing"
        db.commit()

        chat_model = None
        try:
            chat_model = get_chat_model(settings)
        except Exception:
            logger.warning(
                "Could not build a chat model for knowledge enrichment; continuing without it",
                exc_info=True,
            )

        knowledge, chunks = RepositoryScanner(chat_model=chat_model).scan(repository_id, repo_path)
        _persist_knowledge(db, repository_id, knowledge)

        if chunks:
            try:
                _embed_chunks(settings, repository_id, chunks)
            except Exception:
                logger.warning(
                    "Embedding/Qdrant ingestion failed; chat will have no retrieval context",
                    exc_info=True,
                )

        repository.status = "ready"
        db.commit()
    except Exception:
        logger.exception("Analysis pipeline failed for repository %s", repository_id)
        try:
            db.rollback()
            repository = db.get(Repository, repository_id)
            if repository is not None:
                repository.status = "failed"
                db.commit()
        except Exception:
            # If even marking it "failed" fails (e.g. the DB itself is unreachable),
            # don't let that escape uncaught -- BackgroundTasks has no handler above
            # this, and an uncaught exception here would leave the repo stuck in
            # "cloning"/"analyzing" forever with nothing to show for it either way.
            logger.exception(
                "Also failed to mark repository %s as failed", repository_id
            )
    finally:
        db.close()


def _persist_knowledge(db, repository_id: uuid.UUID, knowledge) -> None:
    existing = (
        db.query(RepositoryKnowledgeORM)
        .filter(RepositoryKnowledgeORM.repository_id == repository_id)
        .first()
    )
    fields = knowledge.model_dump(exclude={"id", "created_at"})
    if existing is not None:
        for name, value in fields.items():
            setattr(existing, name, value)
    else:
        db.add(RepositoryKnowledgeORM(**fields))
    db.commit()


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
