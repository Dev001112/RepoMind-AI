"""The analysis orchestrator: a thin loop over PIPELINE, dispatching each
stage through a StageRunner and emitting lifecycle events through an
EventEmitter. Runs as a FastAPI BackgroundTask.

This loop -- specifically the `runner.dispatch(...)` call -- is the whole
"can later be backed by Celery/Redis without major refactoring" extension
point: a future `CeleryStageRunner` swaps in here with zero changes to
`PIPELINE`, any stage function, or `RepositoryStatus`. See ARCHITECTURE.md.

The orchestrator also owns the `AnalysisRun` row: it creates one per run
before dispatching, and flips it to completed/failed/skipped afterwards. The
`run_id` is threaded through StageEvents (the DB record is the cross-stage
state -- nothing in-memory needs to survive a queue boundary).
"""

import logging
import uuid
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.exceptions import PipelineStageError
from app.database.session import SessionLocal
from app.models.orm.repository import Repository
from app.models.schemas.repository import RepositoryStatus
from app.services.repository.pipeline.emitters import DbEventEmitter
from app.services.repository.pipeline.events import (
    ANALYSIS_COMPLETED,
    ANALYSIS_FAILED,
    ANALYSIS_SKIPPED,
    ANALYSIS_STARTED,
    record_event,
)
from app.services.repository.pipeline.incremental import should_skip_analysis
from app.services.repository.pipeline.runs import create_run, finish_run
from app.services.repository.pipeline.stages import PIPELINE
from app.services.repository.pipeline.types import EventEmitter, InProcessRunner, StageEvent, StageRunner

logger = logging.getLogger(__name__)


def run_analysis_pipeline(
    repository_id: uuid.UUID,
    force: bool = False,
    runner: StageRunner | None = None,
    emitter: EventEmitter | None = None,
) -> None:
    settings = get_settings()
    runner = runner or InProcessRunner()
    emitter = emitter or DbEventEmitter()

    run_id = uuid.uuid4()
    started_at = datetime.now(timezone.utc)

    db = SessionLocal()
    try:
        repository = db.get(Repository, repository_id)
        if repository is None:
            logger.warning("run_analysis_pipeline: repository %s not found", repository_id)
            return
        if not force and should_skip_analysis(repository, settings):
            finish_run(
                db, repository_id, run_id, started_at,
                status="skipped", commit_sha=repository.last_analyzed_commit_sha,
            )
            record_event(
                repository_id, ANALYSIS_SKIPPED, run_id=run_id,
                message="unchanged since last analysis; skipped",
            )
            emitter.emit(
                StageEvent(
                    repository_id, RepositoryStatus.READY, "success",
                    message="unchanged since last analysis; skipped",
                    run_id=run_id,
                )
            )
            return
        trigger = "forced" if force else (
            "reanalyze" if repository.last_analyzed_at is not None else "create"
        )
        create_run(db, repository_id, run_id, trigger)
        record_event(
            repository_id, ANALYSIS_STARTED, run_id=run_id,
            data={"trigger": trigger, "force": force},
        )
    finally:
        db.close()

    for stage_def in PIPELINE:
        emitter.emit(StageEvent(repository_id, stage_def.stage, "start", run_id=run_id))
        try:
            runner.dispatch(stage_def, repository_id, settings)
        except Exception as exc:
            error = PipelineStageError(stage_def.stage, repository_id, exc)
            logger.exception(
                "pipeline stage %s failed for repository %s", stage_def.stage.value, repository_id
            )
            record_event(
                repository_id, ANALYSIS_FAILED, run_id=run_id,
                stage=stage_def.stage.value, level="error",
                message=f"{stage_def.stage.value} stage failed",
                data={"error": str(exc)},
            )
            _finish_run(repository_id, run_id, started_at, "failed", error=str(exc))
            emitter.emit(StageEvent(repository_id, stage_def.stage, "failure", error=error, run_id=run_id))
            return
        emitter.emit(StageEvent(repository_id, stage_def.stage, "success", run_id=run_id))

    db = SessionLocal()
    try:
        commit_sha = None
        repository = db.get(Repository, repository_id)
        if repository is not None:
            commit_sha = repository.last_analyzed_commit_sha
    finally:
        db.close()
    _finish_run(repository_id, run_id, started_at, "completed", commit_sha=commit_sha)
    record_event(
        repository_id, ANALYSIS_COMPLETED, run_id=run_id,
        message="analysis completed",
    )
    emitter.emit(StageEvent(repository_id, RepositoryStatus.READY, "success", run_id=run_id))


def _finish_run(
    repository_id: uuid.UUID,
    run_id: uuid.UUID,
    started_at: datetime,
    status: str,
    error: str | None = None,
    commit_sha: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        finish_run(
            db, repository_id, run_id, started_at,
            status=status, error=error, commit_sha=commit_sha,
        )
    finally:
        db.close()
