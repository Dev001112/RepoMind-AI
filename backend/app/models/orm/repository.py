"""ORM model for a submitted repository (either a git URL or an uploaded zip)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    upload_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    # one of: "pending", "cloning", "scanning", "knowledge_built", "embedding", "ready", "failed"
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    local_path: Mapped[str | None] = mapped_column(String, nullable=True)

    # Populated on stage failure by DbEventEmitter -- see app/services/repository/pipeline.
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_stage: Mapped[str | None] = mapped_column(String, nullable=True)

    # Incremental re-analysis short-circuit: set on a successful run, compared
    # against on the next `reanalyze` call before paying for a full re-clone/re-scan.
    last_analyzed_commit_sha: Mapped[str | None] = mapped_column(String, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
