"""ORM model for a submitted repository (either a git URL or an uploaded zip)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    upload_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    # one of: "pending", "cloning", "analyzing", "ready", "failed"
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    local_path: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
