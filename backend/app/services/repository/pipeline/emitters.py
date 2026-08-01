"""The default (and, today, only) EventEmitter: updates the Repository row,
appends to the `analysis_events` log, and logs with structured `extra=`
fields. No new logging dependency -- `extra=` on the stdlib logger is the
full "structured logging" ask for a single process with no log aggregator
yet; swap the Formatter in app/core/logging.py later if that changes, not
these call sites.

Only one consumer exists, so this is the sole EventEmitter implementation --
add a listener registry only when a second one (e.g. a WebSocket push) is
real, not speculatively now. A future consumer can subscribe to the same
`analysis_events` table instead.
"""

import logging
from datetime import datetime, timezone

from app.database.session import SessionLocal
from app.models.orm.repository import Repository
from app.services.repository.pipeline.events import record_event
from app.services.repository.pipeline.types import EventEmitter, StageEvent

logger = logging.getLogger(__name__)


class DbEventEmitter(EventEmitter):
    def emit(self, event: StageEvent) -> None:
        db = SessionLocal()
        try:
            repository = db.get(Repository, event.repository_id)
            if repository is None:
                return
            if event.kind in ("start", "success"):
                repository.status = event.stage.value
            if event.kind == "success" and event.stage.value == "ready":
                repository.last_analyzed_at = datetime.now(timezone.utc)
            if event.kind == "failure":
                repository.status = "failed"
                if event.error is not None:
                    repository.last_error = str(event.error.original)
                    repository.last_error_stage = event.error.stage.value
            db.commit()
        finally:
            db.close()

        level = logging.ERROR if event.kind == "failure" else logging.INFO
        detail = f" error={event.error.original}" if event.error else (
            f" ({event.message})" if event.message else ""
        )
        logger.log(
            level,
            "pipeline stage=%s event=%s repository=%s%s",
            event.stage.value,
            event.kind,
            event.repository_id,
            detail,
            extra={"repository_id": str(event.repository_id), "stage": event.stage.value},
        )

        event_name = event.name or f"{event.stage.value}.{event.kind}"
        record_event(
            event.repository_id,
            event_name,
            run_id=event.run_id,
            stage=event.stage.value,
            level="error" if event.kind == "failure" else "info",
            message=event.message or (str(event.error.original) if event.error else None),
            data={"error": str(event.error.original)} if event.error else None,
        )
