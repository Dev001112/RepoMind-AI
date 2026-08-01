"""Core types for the event-driven analysis pipeline.

Each stage is a plain function of `(repository_id, settings)` -- deliberately
NOT a shared mutable context object holding a live DB session or LLM
Runnable, since those can't cross a future process/queue boundary but
`repository_id`/`Settings` can. See ARCHITECTURE.md for the extension-point
rationale (the seam a future Celery/Redis runner would replace).
"""

import uuid
from dataclasses import dataclass
from typing import Callable, Literal, Protocol

from app.core.config import Settings
from app.core.exceptions import PipelineStageError
from app.models.schemas.repository import RepositoryStatus


@dataclass(frozen=True)
class StageEvent:
    repository_id: uuid.UUID
    stage: RepositoryStatus
    kind: Literal["start", "success", "failure"]
    message: str | None = None
    error: PipelineStageError | None = None
    # The AnalysisRun this event belongs to -- set by the orchestrator.
    run_id: uuid.UUID | None = None
    # Event-log name override; defaults to f"{stage}.{kind}" in the emitter.
    name: str | None = None


class EventEmitter(Protocol):
    def emit(self, event: StageEvent) -> None: ...


@dataclass(frozen=True)
class StageDef:
    stage: RepositoryStatus
    run: Callable[[uuid.UUID, Settings], None]


class StageRunner(Protocol):
    """The Celery/Redis extension seam: swap the implementation that
    dispatches a stage without changing `PIPELINE`, `StageDef`, or any
    stage body itself."""

    def dispatch(self, stage_def: StageDef, repository_id: uuid.UUID, settings: Settings) -> None: ...


class InProcessRunner:
    """Today's only runner -- calls the stage directly, no queue involved."""

    def dispatch(self, stage_def: StageDef, repository_id: uuid.UUID, settings: Settings) -> None:
        stage_def.run(repository_id, settings)
