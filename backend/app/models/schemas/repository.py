"""Pydantic schemas for the Repository API surface."""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import HttpUrl

from app.models.schemas.base import CamelModel


class RepositoryStatus(StrEnum):
    PENDING = "pending"
    CLONING = "cloning"
    SCANNING = "scanning"
    KNOWLEDGE_BUILT = "knowledge_built"
    EMBEDDING = "embedding"
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
    last_error: str | None = None
    last_error_stage: str | None = None
    last_analyzed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RepositoryCardRead(CamelModel):
    """One dashboard card: repository row + the lightweight knowledge stats
    that make a card worth looking at (languages, frameworks, key metrics).
    Assembled by app.services.repository.dashboard -- never reads repo files."""

    id: uuid.UUID
    source_url: str | None = None
    upload_filename: str | None = None
    status: RepositoryStatus
    last_analyzed_at: datetime | None = None
    created_at: datetime
    knowledge_name: str | None = None
    languages: list[str] = []
    frameworks: list[str] = []
    metrics: dict[str, float] = {}
