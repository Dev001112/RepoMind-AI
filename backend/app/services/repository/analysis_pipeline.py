"""The analysis orchestrator: a thin loop over PIPELINE, dispatching each
stage through a StageRunner and emitting lifecycle events through an
EventEmitter. Runs as a FastAPI BackgroundTask.

This loop -- specifically the `runner.dispatch(...)` call -- is the whole
"can later be backed by Celery/Redis without major refactoring" extension
point: a future `CeleryStageRunner` swaps in here with zero changes to
`PIPELINE`, any stage function, or `RepositoryStatus`. See ARCHITECTURE.md.
"""

import logging
import uuid

from app.core.config import get_settings
from app.core.exceptions import PipelineStageError
from app.database.session import SessionLocal
from app.models.orm.repository import Repository
from app.models.schemas.repository import RepositoryStatus
from app.services.repository.pipeline.emitters import DbEventEmitter
from app.services.repository.pipeline.incremental import should_skip_analysis
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

    db = SessionLocal()
    try:
        repository = db.get(Repository, repository_id)
        if repository is None:
            logger.warning("run_analysis_pipeline: repository %s not found", repository_id)
            return
        if not force and should_skip_analysis(repository, settings):
            emitter.emit(
                StageEvent(
                    repository_id, RepositoryStatus.READY, "success",
                    message="unchanged since last analysis; skipped",
                )
            )
            return
    finally:
        db.close()

    for stage_def in PIPELINE:
        emitter.emit(StageEvent(repository_id, stage_def.stage, "start"))
        try:
            runner.dispatch(stage_def, repository_id, settings)
        except Exception as exc:
            error = PipelineStageError(stage_def.stage, repository_id, exc)
            logger.exception(
                "pipeline stage %s failed for repository %s", stage_def.stage.value, repository_id
            )
            emitter.emit(StageEvent(repository_id, stage_def.stage, "failure", error=error))
            return
        emitter.emit(StageEvent(repository_id, stage_def.stage, "success"))

    emitter.emit(StageEvent(repository_id, RepositoryStatus.READY, "success"))
