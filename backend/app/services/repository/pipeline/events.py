"""The analysis event log: canonical event names plus persistence.

The append-only `analysis_events` table is the trace of what happened during
a run -- RepositoryCloned, DetectorStarted/Completed, KnowledgeStored,
AnalysisFailed, ... -- so the frontend can render live progress, debugging
can reconstruct any run, and a future Celery/Redis/WebSocket consumer can
subscribe to the same stream without the pipeline code changing.

`record_event` is deliberately fire-and-forget: the event log must never
take the analysis down (the DB write is wrapped, not bubbled).
"""

import logging
import uuid

from app.database.session import SessionLocal
from app.models.orm.analysis import AnalysisEvent

logger = logging.getLogger(__name__)

# Milestone event vocabulary (ARCHITECTURE.md "Analysis Events").
ANALYSIS_STARTED = "AnalysisStarted"
ANALYSIS_SKIPPED = "AnalysisSkipped"
ANALYSIS_COMPLETED = "AnalysisCompleted"
ANALYSIS_FAILED = "AnalysisFailed"
REPOSITORY_CLONED = "RepositoryCloned"
DETECTOR_STARTED = "DetectorStarted"
DETECTOR_COMPLETED = "DetectorCompleted"
KNOWLEDGE_BUILT = "KnowledgeBuilt"
KNOWLEDGE_STORED = "KnowledgeStored"
# Phase 3.2 (Semantic Knowledge Index): emitted by the embedding stage, in
# order, so progress can show the indexing granularly instead of one spinner.
KNOWLEDGE_CHUNKS_BUILT = "KnowledgeChunksBuilt"
EMBEDDINGS_GENERATED = "EmbeddingsGenerated"
VECTOR_INDEX_UPDATED = "VectorIndexUpdated"


def record_event(
    repository_id: uuid.UUID,
    event_name: str,
    run_id: uuid.UUID | None = None,
    stage: str | None = None,
    level: str = "info",
    message: str | None = None,
    data: dict | None = None,
) -> None:
    """Append one event to the log. Never raises -- the pipeline must survive
    a failing event store (DB down is handled by the stage's own failure path)."""
    db = SessionLocal()
    try:
        db.add(
            AnalysisEvent(
                repository_id=repository_id,
                run_id=run_id,
                event_name=event_name,
                stage=stage,
                level=level,
                message=message,
                data=data or {},
            )
        )
        db.commit()
    except Exception:
        logger.exception(
            "record_event: failed to persist %s for repository %s", event_name, repository_id
        )
    finally:
        db.close()


class DetectorEventSink:
    """Adapter the scanner calls for per-detector lifecycle events.

    Created by the scanning stage with the current run's id; the scanner
    itself stays DB-agnostic and just calls `started`/`completed` through a
    small Protocol (see app.services.repository.scanner)."""

    def __init__(self, repository_id: uuid.UUID, run_id: uuid.UUID | None) -> None:
        self.repository_id = repository_id
        self.run_id = run_id

    def started(self, detector_name: str) -> None:
        record_event(
            self.repository_id,
            DETECTOR_STARTED,
            run_id=self.run_id,
            stage="scanning",
            message=f"{detector_name} started",
            data={"detector": detector_name},
        )

    def completed(
        self,
        detector_name: str,
        duration_ms: int,
        errors: list[str],
        warnings: list[str],
    ) -> None:
        record_event(
            self.repository_id,
            DETECTOR_COMPLETED,
            run_id=self.run_id,
            stage="scanning",
            level="warning" if errors else "info",
            message=f"{detector_name} completed in {duration_ms}ms"
            + (f" with {len(errors)} error(s)" if errors else ""),
            data={"detector": detector_name, "duration_ms": duration_ms},
        )
