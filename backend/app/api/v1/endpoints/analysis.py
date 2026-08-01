"""Analysis observability endpoints: live progress, metrics, run history,
the event log, and the raw detector results of the latest run.

These are the read-side of the Repository Knowledge layer -- the frontend
polls /progress while analysis runs, and surfaces metrics/history afterwards.
Detector outputs are kept for debugging (and future re-analysis diffing), per
ARCHITECTURE.md: "Detector outputs should be stored. Not only the final
knowledge."
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.exceptions import RepositoryNotFoundError
from app.models.orm.analysis import (
    AnalysisEvent,
    AnalysisRun,
    DetectorResultRecord,
)
from app.models.orm.repository import Repository
from app.models.schemas.analysis import (
    AnalysisEventRead,
    AnalysisRunRead,
    DetectorResultRead,
    MetricRead,
    ProgressResponse,
)
from app.services.repository.metrics import load_metrics
from app.services.repository.progress import compute_progress

router = APIRouter()


def _require_repository(db: Session, repository_id: uuid.UUID) -> Repository:
    repository = db.get(Repository, repository_id)
    if repository is None:
        raise RepositoryNotFoundError(str(repository_id))
    return repository


@router.get("/repositories/{repository_id}/progress", response_model=ProgressResponse)
def get_repository_progress(
    repository_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Streamable per-stage/per-detector progress for the frontend progress UI."""
    repository = _require_repository(db, repository_id)
    return compute_progress(db, repository)


@router.get("/repositories/{repository_id}/metrics", response_model=list[MetricRead])
def get_repository_metrics(
    repository_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
):
    """Scalar dashboard figures (files, symbols, endpoints, ...) from the
    latest run's knowledge."""
    _require_repository(db, repository_id)
    return load_metrics(db, repository_id)


@router.get("/repositories/{repository_id}/analysis", response_model=list[AnalysisRunRead])
def get_repository_analysis_runs(
    repository_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """Run history, newest first -- when each analysis ran, how long it took,
    and whether it completed, failed, or was skipped."""
    _require_repository(db, repository_id)
    return (
        db.query(AnalysisRun)
        .filter(AnalysisRun.repository_id == repository_id)
        .order_by(desc(AnalysisRun.started_at))
        .limit(limit)
        .all()
    )


@router.get("/repositories/{repository_id}/events", response_model=list[AnalysisEventRead])
def get_repository_events(
    repository_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    """The append-only event log (RepositoryCloned, DetectorStarted, ...),
    newest first."""
    _require_repository(db, repository_id)
    return (
        db.query(AnalysisEvent)
        .filter(AnalysisEvent.repository_id == repository_id)
        .order_by(desc(AnalysisEvent.created_at))
        .limit(limit)
        .all()
    )


@router.get("/repositories/{repository_id}/detectors", response_model=list[DetectorResultRead])
def get_repository_detector_results(
    repository_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
):
    """Raw typed output of every detector from the latest run -- the debugging
    surface for "why did the knowledge come out this way?"."""
    _require_repository(db, repository_id)
    return (
        db.query(DetectorResultRecord)
        .filter(DetectorResultRecord.repository_id == repository_id)
        .order_by(DetectorResultRecord.detector_name)
        .all()
    )
