"""ORM model for the retrieval history: one row per intelligent-retrieval run,
so the UI can show query history and the metrics endpoint can aggregate
latency, cache hits and intent mix per repository.

This is a write-mostly log -- retrieval performance is not a correctness
path, so nothing in the pipeline blocks on it (the engine hands the row to
the API layer, which persists it best-effort).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class RetrievalQueryRecord(Base):
    __tablename__ = "retrieval_queries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id"), nullable=False, index=True
    )
    query: Mapped[str] = mapped_column(String, nullable=False)
    rewritten_query: Mapped[str | None] = mapped_column(String, nullable=True)
    intent: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False, default="auto")
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
