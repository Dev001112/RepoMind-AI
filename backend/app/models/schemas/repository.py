"""Pydantic schemas for the Repository API surface."""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import HttpUrl

from app.models.schemas.base import CamelModel


class RepositoryStatus(StrEnum):
    PENDING = "pending"
    CLONING = "cloning"
    ANALYZING = "analyzing"
    READY = "ready"
    FAILED = "failed"


class RepositoryCreate(CamelModel):
    source_url: HttpUrl


class RepositoryRead(CamelModel):
    id: uuid.UUID
    source_url: str | None = None
    upload_filename: str | None = None
    status: RepositoryStatus
    local_path: str | None = None
    created_at: datetime
    updated_at: datetime
