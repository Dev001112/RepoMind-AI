"""The pipeline stages, split at the seams the original single
`run_analysis_pipeline` function already had. Each stage takes only
`(repository_id, settings)` and opens its own `SessionLocal()` -- no state
passes between stages in-memory, so every stage is already safe behind a
future queue boundary with zero changes. The one place this would otherwise
matter (SCANNING producing chunks that EMBEDDING needs) is resolved by
EMBEDDING re-deriving its input from the persisted RepositoryKnowledge
report (`load_knowledge` + the Phase 3.2 chunk builder) rather than receiving
it -- deterministic, local CPU, so paying for it twice is a non-issue and
keeps the stage boundary real today instead of a "fix later" gap.

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

from app.ai.embeddings.factory import get_embeddings
from app.ai.llm.factory import get_chat_model
from app.core.config import Settings
from app.database.session import SessionLocal
from app.models.orm.repository import Repository
from app.models.schemas.repository import RepositoryStatus
from app.services.knowledge.chunk_builder import build_knowledge_chunks
from app.services.knowledge.embedding_service import index_knowledge_chunks
from app.services.knowledge_builder.persistence import (
    load_knowledge,
    persist_detector_results,
    persist_knowledge,
)
from app.services.repository.clone.github_cloner import GithubCloner
from app.services.repository.clone.zip_extractor import ZipExtractor
from app.services.repository.metrics import persist_metrics
from app.services.repository.pipeline.events import (
    EMBEDDINGS_GENERATED,
    KNOWLEDGE_BUILT,
    KNOWLEDGE_CHUNKS_BUILT,
    KNOWLEDGE_STORED,
    VECTOR_INDEX_UPDATED,
    DetectorEventSink,
    record_event,
)
from app.services.repository.pipeline.runs import latest_running_run_id
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
        run_id = latest_running_run_id(db, repository_id)
    finally:
        db.close()

    chat_model = None
    try:
        chat_model = get_chat_model(settings)
    except Exception:
        logger.warning(
            "Could not build a chat model for knowledge enrichment; continuing without it",
            exc_info=True,
        )

    sink = DetectorEventSink(repository_id, run_id)
    knowledge, _chunks, detector_results = RepositoryScanner(
        chat_model=chat_model
    ).scan(repository_id, repo_path, sink=sink)
    record_event(
        repository_id, KNOWLEDGE_BUILT, run_id=run_id,
        stage="scanning", message="repository knowledge assembled",
    )

    db = SessionLocal()
    try:
        persist_detector_results(db, repository_id, run_id, detector_results)
        persist_knowledge(db, repository_id, knowledge)
        persist_metrics(db, repository_id, run_id, knowledge)
        repository = db.get(Repository, repository_id)
        if repository is None:
            raise RuntimeError(f"repository {repository_id} not found")
        repository.status = RepositoryStatus.KNOWLEDGE_BUILT.value
        db.commit()
    finally:
        db.close()
    record_event(
        repository_id, KNOWLEDGE_STORED, run_id=run_id,
        stage="scanning", message="repository knowledge persisted",
    )


def run_embedding_stage(repository_id: uuid.UUID, settings: Settings) -> None:
    """Build semantic KnowledgeChunks from the persisted knowledge and index
    them into Qdrant -- batched, incremental (checksums), never blocking on
    the LLM. Replaces the Phase 2 file-chunk embedding: the index now holds
    knowledge, not raw source slices; stale Phase 2 points are swept by the
    indexing service itself (add-then-delete, so a failure mid-way leaves the
    previous index intact)."""
    db = SessionLocal()
    try:
        repository = db.get(Repository, repository_id)
        if repository is None:
            raise RuntimeError(f"repository {repository_id} not found")
        knowledge = load_knowledge(db, repository_id)
        run_id = latest_running_run_id(db, repository_id)
    finally:
        db.close()

    chunks = build_knowledge_chunks(repository_id, knowledge) if knowledge else []
    record_event(
        repository_id, KNOWLEDGE_CHUNKS_BUILT, run_id=run_id, stage="embedding",
        message=f"{len(chunks)} knowledge chunks built from the analysis report",
        data={"chunk_count": len(chunks)},
    )
    if not chunks:
        # Nothing to index (empty knowledge report). Leave whatever is already
        # there alone -- an LLM enrichment outage must not nuke a working index.
        logger.info(
            "embedding stage: no knowledge chunks for repository %s -- skipping",
            repository_id,
        )
        return

    try:
        embeddings = get_embeddings(settings)
    except Exception:
        logger.exception("embedding stage: could not build an embedding provider")
        raise

    index_run_id = str(uuid.uuid4())
    stats = index_knowledge_chunks(
        settings, repository_id, chunks, embeddings, run_id=index_run_id
    )
    record_event(
        repository_id, EMBEDDINGS_GENERATED, run_id=run_id, stage="embedding",
        message=f"embedded {stats.embedded} chunks, skipped {stats.skipped} unchanged, "
        f"removed {stats.removed} stale",
        data={
            "embedded": stats.embedded, "skipped": stats.skipped,
            "removed": stats.removed, "index_run_id": index_run_id,
        },
    )
    record_event(
        repository_id, VECTOR_INDEX_UPDATED, run_id=run_id, stage="embedding",
        message="vector index up to date",
        data={"total_chunks": stats.total},
    )


PIPELINE: list[StageDef] = [
    StageDef(RepositoryStatus.CLONING, run_cloning_stage),
    StageDef(RepositoryStatus.SCANNING, run_scanning_and_knowledge_stage),
    StageDef(RepositoryStatus.EMBEDDING, run_embedding_stage),
]
