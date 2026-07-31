"""The structured 'Repository Knowledge' object -- the canonical source of
truth for what RepoMind AI knows about a repository once analysis has run.

Composed of one section per facet (metadata, languages, frameworks, ...) so
every consumer -- chat, search, reports, future agents -- reads a named,
typed section instead of reaching into a flat bag of fields or, worse, the
raw repository itself. See ARCHITECTURE.md for the full rationale.
"""

import uuid
from datetime import datetime

from app.models.schemas.base import CamelModel


class ApiEndpoint(CamelModel):
    method: str | None = None
    path: str | None = None
    file: str


class LanguageStat(CamelModel):
    name: str
    file_count: int


class MetadataSection(CamelModel):
    name: str | None = None
    description: str | None = None
    repository_type: str | None = None
    license: str | None = None
    main_entry_point: str | None = None
    analyzed_at: datetime | None = None


class LanguagesSection(CamelModel):
    languages: list[str] = []
    stats: list[LanguageStat] = []


class FrameworksSection(CamelModel):
    frameworks: list[str] = []


class DependenciesSection(CamelModel):
    dependencies: dict[str, str] = {}
    package_managers: list[str] = []
    libraries: list[str] = []


class ArchitectureSection(CamelModel):
    summary: str | None = None
    folder_structure: dict = {}
    production_readiness: str | None = None
    difficulty_level: str | None = None
    use_cases: list[str] = []
    potential_applications: list[str] = []


class FilesSection(CamelModel):
    total_files: int = 0
    folder_structure: dict = {}


class SymbolsSection(CamelModel):
    total_symbols: int = 0


class ImportsSection(CamelModel):
    dependency_graph: dict[str, list[str]] = {}


class ApisSection(CamelModel):
    endpoints: list[ApiEndpoint] = []


class DatabasesSection(CamelModel):
    databases: list[str] = []
    orms: list[str] = []


class DockerSection(CamelModel):
    docker_support: bool | None = None
    dockerfile_path: str | None = None
    compose_services: list[str] = []


class CudaSection(CamelModel):
    gpu_required: bool | None = None
    cuda_required: bool | None = None


class CiCdSection(CamelModel):
    providers: list[str] = []
    workflow_files: list[str] = []


class DeploymentSection(CamelModel):
    platforms: list[str] = []


class TestingSection(CamelModel):
    frameworks: list[str] = []
    has_tests: bool = False
    test_file_count: int = 0


class DocumentationSection(CamelModel):
    has_readme: bool = False
    installation_steps: list[str] = []
    has_contributing: bool = False
    has_license_file: bool = False


class PerformanceSection(CamelModel):
    notes: list[str] = []


class SecuritySection(CamelModel):
    findings: list[str] = []


class QualitySection(CamelModel):
    """Cheap size/hygiene heuristics -- not a real static-analysis quality score."""

    total_files: int = 0
    total_lines: int = 0
    todo_count: int = 0


class RepositoryKnowledge(CamelModel):
    id: uuid.UUID | None = None
    repository_id: uuid.UUID

    metadata: MetadataSection = MetadataSection()
    languages: LanguagesSection = LanguagesSection()
    frameworks: FrameworksSection = FrameworksSection()
    dependencies: DependenciesSection = DependenciesSection()
    architecture: ArchitectureSection = ArchitectureSection()
    files: FilesSection = FilesSection()
    symbols: SymbolsSection = SymbolsSection()
    imports: ImportsSection = ImportsSection()
    apis: ApisSection = ApisSection()
    databases: DatabasesSection = DatabasesSection()
    docker: DockerSection = DockerSection()
    cuda: CudaSection = CudaSection()
    cicd: CiCdSection = CiCdSection()
    deployment: DeploymentSection = DeploymentSection()
    testing: TestingSection = TestingSection()
    documentation: DocumentationSection = DocumentationSection()
    performance: PerformanceSection = PerformanceSection()
    security: SecuritySection = SecuritySection()
    quality: QualitySection = QualitySection()

    created_at: datetime | None = None
