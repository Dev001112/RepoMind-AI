"""ORM models for the analysis observability layer: one row per analysis run,
per emitted event, per detector result, and per computed metric.

These tables exist so the pipeline's *trace* is stored, not just its final
output: `analysis_runs` anchors a run, `analysis_events` is the append-only
event log (RepositoryCloned, DetectorStarted, KnowledgeBuilt, ...), and
`detector_results` keeps the raw typed output of every detector for
debugging and re-analysis diffing. `repository_metrics` holds the small set
of scalar, filterable figures surfaced on the dashboard (files, symbols,
endpoints, ...). See ARCHITECTURE.md.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base

JSONVariant = JSON().with_variant(JSONB, "postgresql")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id"), nullable=False, index=True
    )
    # one of: "running", "completed", "failed", "skipped"
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    # how this run was triggered: "create" | "reanalyze" | "forced"
    trigger: Mapped[str] = mapped_column(String, nullable=False, default="create")
    commit_sha: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)


class AnalysisEvent(Base):
    __tablename__ = "analysis_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    # event name, e.g. "RepositoryCloned", "DetectorStarted", "KnowledgeStored"
    event_name: Mapped[str] = mapped_column(String, nullable=False)
    stage: Mapped[str | None] = mapped_column(String, nullable=True)
    level: Mapped[str] = mapped_column(String, nullable=False, default="info")
    message: Mapped[str | None] = mapped_column(String, nullable=True)
    # any structured payload (detector durations, error details, ...)
    data: Mapped[dict] = mapped_column(JSONVariant, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DetectorResultRecord(Base):
    __tablename__ = "detector_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    detector_name: Mapped[str] = mapped_column(String, nullable=False)
    detector_version: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warnings: Mapped[list] = mapped_column(JSONVariant, nullable=False, default=list)
    errors: Mapped[list] = mapped_column(JSONVariant, nullable=False, default=list)
    # the detector's typed payload, serialized to JSON
    payload: Mapped[dict] = mapped_column(JSONVariant, nullable=False, default=dict)


class RepositoryMetric(Base):
    __tablename__ = "repository_metrics"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    metric_name: Mapped[str] = mapped_column(String, nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
