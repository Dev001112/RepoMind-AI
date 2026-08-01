"""Pydantic schemas for the analysis observability endpoints: progress,
metrics, run history, the event log, and persisted detector results."""

import uuid
from datetime import datetime

from app.models.schemas.base import CamelModel


class AnalysisRunRead(CamelModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    status: str
    trigger: str
    commit_sha: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error: str | None = None


class AnalysisEventRead(CamelModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    run_id: uuid.UUID | None = None
    event_name: str
    stage: str | None = None
    level: str
    message: str | None = None
    data: dict = {}
    created_at: datetime


class DetectorResultRead(CamelModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    run_id: uuid.UUID | None = None
    detector_name: str
    detector_version: str
    confidence: float
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    warnings: list[str] = []
    errors: list[str] = []
    payload: dict = {}


class MetricRead(CamelModel):
    metric_name: str
    metric_value: float
    unit: str | None = None


class DetectorProgress(CamelModel):
    name: str
    label: str
    percent: int


class StageProgress(CamelModel):
    name: str
    label: str
    percent: int
    state: str  # done | active | queued | failed
    detectors: list[DetectorProgress] = []


class ProgressResponse(CamelModel):
    status: str
    overall_percent: int
    stages: list[StageProgress]
    message: str | None = None
