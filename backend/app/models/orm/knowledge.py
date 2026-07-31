"""ORM model for the structured 'Repository Knowledge' object.

Column set mirrors app.models.schemas.knowledge.RepositoryKnowledge -- that
pydantic schema is the source of truth for the field list.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class RepositoryKnowledge(Base):
    __tablename__ = "repository_knowledge"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id"), nullable=False
    )

    name: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    repository_type: Mapped[str | None] = mapped_column(String, nullable=True)

    # JSON (not the Postgres-only ARRAY/JSONB) so this works on SQLite now and
    # Postgres later with no code change -- just less indexable there.
    languages: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    frameworks: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    libraries: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    dependencies: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    gpu_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cuda_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    docker_support: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    installation_steps: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    package_managers: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    production_readiness: Mapped[str | None] = mapped_column(String, nullable=True)
    difficulty_level: Mapped[str | None] = mapped_column(String, nullable=True)
    architecture_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    folder_structure: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    main_entry_point: Mapped[str | None] = mapped_column(String, nullable=True)

    use_cases: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    potential_applications: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    license: Mapped[str | None] = mapped_column(String, nullable=True)

    # Phase 3
    security_findings: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    performance_notes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    # {file_path: [imported module/file names]} -- feeds a future dependency graph
    # visualization; not resolved to exact repo-relative paths, just raw import targets.
    dependency_graph: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
