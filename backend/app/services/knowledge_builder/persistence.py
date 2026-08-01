"""Round-trips a RepositoryKnowledge object to/from PostgreSQL/SQLite.

Promoted scalar fields and the `languages`/`frameworks`/`dependencies`
child-table rows are written/read explicitly; every other section is stored
as one JSON(B) blob column and rebuilt via that section's own
`model_validate()` -- see app/models/orm/knowledge.py for why this
normalization boundary was chosen.
"""

import uuid

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.orm.analysis import DetectorResultRecord
from app.models.orm.knowledge import (
    RepositoryDependency,
    RepositoryFramework,
    RepositoryKnowledge as RepositoryKnowledgeORM,
    RepositoryLanguage,
)
from app.models.schemas.knowledge import (
    ApisSection,
    ArchitectureSection,
    CiCdSection,
    CudaSection,
    DatabasesSection,
    DependenciesSection,
    DeploymentSection,
    DocumentationSection,
    DockerSection,
    FilesSection,
    FrameworksSection,
    ImportsSection,
    LanguageStat,
    LanguagesSection,
    MetadataSection,
    PerformanceSection,
    QualitySection,
    RepositoryKnowledge,
    SecuritySection,
    SymbolsSection,
    TestingSection,
)
from app.services.repository.detectors.base import DetectorResult


def persist_knowledge(db: Session, repository_id: uuid.UUID, knowledge: RepositoryKnowledge) -> None:
    row = (
        db.query(RepositoryKnowledgeORM)
        .filter(RepositoryKnowledgeORM.repository_id == repository_id)
        .first()
    )
    if row is None:
        row = RepositoryKnowledgeORM(repository_id=repository_id)
        db.add(row)

    row.name = knowledge.metadata.name
    row.description = knowledge.metadata.description
    row.repository_type = knowledge.metadata.repository_type
    row.license = knowledge.metadata.license
    row.main_entry_point = knowledge.metadata.main_entry_point
    row.production_readiness = knowledge.architecture.production_readiness
    row.difficulty_level = knowledge.architecture.difficulty_level
    row.gpu_required = knowledge.cuda.gpu_required
    row.cuda_required = knowledge.cuda.cuda_required
    row.docker_support = knowledge.docker.docker_support
    row.analyzed_at = knowledge.metadata.analyzed_at
    row.package_managers = knowledge.dependencies.package_managers

    row.architecture = knowledge.architecture.model_dump(mode="json")
    row.files = knowledge.files.model_dump(mode="json")
    row.symbols = knowledge.symbols.model_dump(mode="json")
    row.imports = knowledge.imports.model_dump(mode="json")
    row.apis = knowledge.apis.model_dump(mode="json")
    row.databases = knowledge.databases.model_dump(mode="json")
    row.docker = knowledge.docker.model_dump(mode="json")  # kept for symmetry/debugging even though promoted scalars above are authoritative
    row.cicd = knowledge.cicd.model_dump(mode="json")
    row.deployment = knowledge.deployment.model_dump(mode="json")
    row.testing = knowledge.testing.model_dump(mode="json")
    row.documentation = knowledge.documentation.model_dump(mode="json")
    row.performance = knowledge.performance.model_dump(mode="json")
    row.security = knowledge.security.model_dump(mode="json")
    row.quality = knowledge.quality.model_dump(mode="json")

    db.execute(delete(RepositoryLanguage).where(RepositoryLanguage.repository_id == repository_id))
    db.execute(delete(RepositoryFramework).where(RepositoryFramework.repository_id == repository_id))
    db.execute(delete(RepositoryDependency).where(RepositoryDependency.repository_id == repository_id))

    stats_by_name = {stat.name: stat.file_count for stat in knowledge.languages.stats}
    for name in knowledge.languages.languages:
        db.add(
            RepositoryLanguage(
                repository_id=repository_id, name=name, file_count=stats_by_name.get(name, 0)
            )
        )
    for name in knowledge.frameworks.frameworks:
        db.add(RepositoryFramework(repository_id=repository_id, name=name))
    for name, version_spec in knowledge.dependencies.dependencies.items():
        db.add(RepositoryDependency(repository_id=repository_id, name=name, version_spec=version_spec))

    db.commit()


def persist_detector_results(
    db: Session,
    repository_id: uuid.UUID,
    run_id: uuid.UUID | None,
    results: list[DetectorResult],
) -> None:
    """Store the raw typed output of every detector from this run.

    Only the latest run's results are kept (the previous run's rows are
    deleted first) -- the point is debugging *the current* knowledge, not
    building a full result history (that lives in analysis_events/runs).
    """
    db.execute(delete(DetectorResultRecord).where(DetectorResultRecord.repository_id == repository_id))
    for result in results:
        db.add(
            DetectorResultRecord(
                repository_id=repository_id,
                run_id=run_id,
                detector_name=result.detector_name,
                detector_version=result.detector_version,
                confidence=result.confidence,
                started_at=result.started_at,
                finished_at=result.finished_at,
                duration_ms=result.duration_ms,
                warnings=result.warnings,
                errors=result.errors,
                payload=result.data.model_dump(mode="json"),
            )
        )
    db.commit()


def load_knowledge(db: Session, repository_id: uuid.UUID) -> RepositoryKnowledge | None:
    row = (
        db.query(RepositoryKnowledgeORM)
        .filter(RepositoryKnowledgeORM.repository_id == repository_id)
        .first()
    )
    if row is None:
        return None

    languages = (
        db.query(RepositoryLanguage).filter(RepositoryLanguage.repository_id == repository_id).all()
    )
    frameworks = (
        db.query(RepositoryFramework).filter(RepositoryFramework.repository_id == repository_id).all()
    )
    dependencies = (
        db.query(RepositoryDependency).filter(RepositoryDependency.repository_id == repository_id).all()
    )

    return RepositoryKnowledge(
        id=row.id,
        repository_id=row.repository_id,
        metadata=MetadataSection(
            name=row.name,
            description=row.description,
            repository_type=row.repository_type,
            license=row.license,
            main_entry_point=row.main_entry_point,
            analyzed_at=row.analyzed_at,
        ),
        languages=LanguagesSection(
            languages=[lang.name for lang in languages],
            stats=[LanguageStat(name=lang.name, file_count=lang.file_count) for lang in languages],
        ),
        frameworks=FrameworksSection(frameworks=[fw.name for fw in frameworks]),
        dependencies=DependenciesSection(
            dependencies={dep.name: dep.version_spec for dep in dependencies},
            package_managers=row.package_managers or [],
            libraries=sorted(dep.name for dep in dependencies),
        ),
        architecture=ArchitectureSection.model_validate(row.architecture or {}),
        files=FilesSection.model_validate(row.files or {}),
        symbols=SymbolsSection.model_validate(row.symbols or {}),
        imports=ImportsSection.model_validate(row.imports or {}),
        apis=ApisSection.model_validate(row.apis or {}),
        databases=DatabasesSection.model_validate(row.databases or {}),
        docker=DockerSection(
            docker_support=row.docker_support,
            dockerfile_path=(row.docker or {}).get("dockerfile_path"),
            compose_services=(row.docker or {}).get("compose_services", []),
        ),
        cuda=CudaSection(gpu_required=row.gpu_required, cuda_required=row.cuda_required),
        cicd=CiCdSection.model_validate(row.cicd or {}),
        deployment=DeploymentSection.model_validate(row.deployment or {}),
        testing=TestingSection.model_validate(row.testing or {}),
        documentation=DocumentationSection.model_validate(row.documentation or {}),
        performance=PerformanceSection.model_validate(row.performance or {}),
        security=SecuritySection.model_validate(row.security or {}),
        quality=QualitySection.model_validate(row.quality or {}),
        created_at=row.created_at,
    )
