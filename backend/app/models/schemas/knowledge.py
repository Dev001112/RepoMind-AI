"""The structured 'Repository Knowledge' object -- the source-of-truth schema
for what RepoMind AI knows about a repository once analysis has run.

Mirrors app.models.orm.knowledge.RepositoryKnowledge column-for-column.
"""

import uuid
from datetime import datetime

from pydantic import field_validator

from app.models.schemas.base import CamelModel

_LIST_FIELDS = (
    "languages",
    "frameworks",
    "libraries",
    "package_managers",
    "installation_steps",
    "use_cases",
    "potential_applications",
    "security_findings",
    "performance_notes",
)
_DICT_FIELDS = ("dependencies", "folder_structure", "dependency_graph")


class RepositoryKnowledge(CamelModel):
    id: uuid.UUID | None = None
    repository_id: uuid.UUID

    name: str | None = None
    description: str | None = None
    repository_type: str | None = None

    languages: list[str] = []
    frameworks: list[str] = []
    libraries: list[str] = []
    dependencies: dict = {}

    gpu_required: bool | None = None
    cuda_required: bool | None = None
    docker_support: bool | None = None

    installation_steps: list[str] = []
    package_managers: list[str] = []

    production_readiness: str | None = None
    difficulty_level: str | None = None
    architecture_summary: str | None = None
    folder_structure: dict = {}
    main_entry_point: str | None = None

    use_cases: list[str] = []
    potential_applications: list[str] = []
    license: str | None = None

    # Phase 3
    security_findings: list[str] = []
    performance_notes: list[str] = []
    dependency_graph: dict = {}

    created_at: datetime | None = None

    # ORM columns are nullable (nothing populates them until Phase 2 analysis runs) --
    # coerce None to an empty collection so the API never sends `null` where the
    # frontend expects an array/object to iterate over.
    @field_validator(*_LIST_FIELDS, mode="before")
    @classmethod
    def _default_list(cls, value: list | None) -> list:
        return value if value is not None else []

    @field_validator(*_DICT_FIELDS, mode="before")
    @classmethod
    def _default_dict(cls, value: dict | None) -> dict:
        return value if value is not None else {}
