"""ORM models for the structured 'Repository Knowledge' object.

`RepositoryKnowledge` holds promoted scalar columns for the facets read/
filtered most often, plus one JSON(B) column per free-form section --
`.with_variant(JSONB, "postgresql")` gives real JSONB the moment
`DATABASE_URL` becomes a Postgres DSN, and falls back to plain JSON on
SQLite today, no code change either way (same philosophy as everywhere
else in this codebase).

`RepositoryLanguage`/`RepositoryFramework`/`RepositoryDependency` are real
child tables, not JSON -- these are the genuinely tabular, many-to-one,
filterable facets ("find repos using Flask") where normalization is
actually justified; everything else varies too much in shape to be worth
a dedicated table yet. See ARCHITECTURE.md for the full rationale.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base

JSONVariant = JSON().with_variant(JSONB, "postgresql")


class RepositoryKnowledge(Base):
    __tablename__ = "repository_knowledge"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id"), nullable=False, unique=True
    )

    # --- promoted scalars (frequently read directly, no JSON path needed) ---
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    repository_type: Mapped[str | None] = mapped_column(String, nullable=True)
    license: Mapped[str | None] = mapped_column(String, nullable=True)
    main_entry_point: Mapped[str | None] = mapped_column(String, nullable=True)
    production_readiness: Mapped[str | None] = mapped_column(String, nullable=True)
    difficulty_level: Mapped[str | None] = mapped_column(String, nullable=True)
    gpu_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cuda_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    docker_support: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Small enough to not warrant its own child table like languages/frameworks/dependencies.
    package_managers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    # --- one JSON(B) blob per free-form section, each round-tripping via
    # that section's Pydantic model .model_dump()/.model_validate() ---
    architecture: Mapped[dict] = mapped_column(JSONVariant, nullable=False, default=dict)
    files: Mapped[dict] = mapped_column(JSONVariant, nullable=False, default=dict)
    symbols: Mapped[dict] = mapped_column(JSONVariant, nullable=False, default=dict)
    imports: Mapped[dict] = mapped_column(JSONVariant, nullable=False, default=dict)
    apis: Mapped[dict] = mapped_column(JSONVariant, nullable=False, default=dict)
    databases: Mapped[dict] = mapped_column(JSONVariant, nullable=False, default=dict)
    # dockerfile_path/compose_services only -- docker_support itself is the promoted
    # scalar column above (it's the field read/filtered most often).
    docker: Mapped[dict] = mapped_column(JSONVariant, nullable=False, default=dict)
    cicd: Mapped[dict] = mapped_column(JSONVariant, nullable=False, default=dict)
    deployment: Mapped[dict] = mapped_column(JSONVariant, nullable=False, default=dict)
    testing: Mapped[dict] = mapped_column(JSONVariant, nullable=False, default=dict)
    documentation: Mapped[dict] = mapped_column(JSONVariant, nullable=False, default=dict)
    performance: Mapped[dict] = mapped_column(JSONVariant, nullable=False, default=dict)
    security: Mapped[dict] = mapped_column(JSONVariant, nullable=False, default=dict)
    quality: Mapped[dict] = mapped_column(JSONVariant, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RepositoryLanguage(Base):
    __tablename__ = "repository_languages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    file_count: Mapped[int] = mapped_column(nullable=False, default=0)


class RepositoryFramework(Base):
    __tablename__ = "repository_frameworks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)


class RepositoryDependency(Base):
    __tablename__ = "repository_dependencies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    version_spec: Mapped[str] = mapped_column(String, nullable=False)
