"""AnalysisRun lifecycle helpers.

The orchestrator owns the run row: it creates one `running` row before
dispatching stages and flips it to `completed`/`failed`/`skipped` afterwards.
Stages that need the current run id (scanning, for detector results/events)
look it up from the DB -- `(repository_id, settings)` stays the only state
that crosses stage boundaries, so the Celery seam holds (see ARCHITECTURE.md).
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.orm.analysis import AnalysisRun

logger = logging.getLogger(__name__)


def create_run(db: Session, repository_id: uuid.UUID, run_id: uuid.UUID, trigger: str) -> None:
    db.add(
        AnalysisRun(
            id=run_id,
            repository_id=repository_id,
            status="running",
            trigger=trigger,
            started_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


def finish_run(
    db: Session,
    repository_id: uuid.UUID,
    run_id: uuid.UUID,
    started_at: datetime,
    status: str = "completed",
    error: str | None = None,
    commit_sha: str | None = None,
) -> None:
    run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.id == run_id, AnalysisRun.repository_id == repository_id)
        .first()
    )
    if run is None:
        logger.warning("finish_run: run %s not found for repository %s", run_id, repository_id)
        return
    run.status = status
    run.finished_at = datetime.now(timezone.utc)
    run.duration_ms = max(
        0, round((run.finished_at - started_at).total_seconds() * 1000)
    )
    if error is not None:
        run.error = error[:500]
    if commit_sha is not None:
        run.commit_sha = commit_sha
    db.commit()


def latest_running_run_id(db: Session, repository_id: uuid.UUID) -> uuid.UUID | None:
    """The most recent not-yet-finished run for this repository -- i.e. the
    run the orchestrator created right before dispatching the current stage."""
    run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.repository_id == repository_id, AnalysisRun.status == "running")
        .order_by(desc(AnalysisRun.started_at))
        .first()
    )
    return run.id if run is not None else None
