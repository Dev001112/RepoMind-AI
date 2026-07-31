"""Builds the canonical RepositoryKnowledge object from every detector's
typed result plus the tree-sitter/import-graph output.

Deterministic sections are pure assembly -- placing each DetectorResult's
`.data` into its matching section. A handful of judgment fields that
genuinely can't be extracted deterministically (architecture summary, use
cases, potential applications, production readiness, difficulty level,
performance notes) are filled in by one best-effort LLM call; if that call
fails for any reason (no provider configured, quota, network, malformed
output), those fields are simply left None/empty rather than failing the
whole pipeline. Any detector-level errors are logged here (with the
detector's name) so a bad detector run is visible without crashing assembly.
"""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable

from app.ai.chains.knowledge_enrichment_chain import (
    KnowledgeEnrichment,
    build_knowledge_enrichment_chain,
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
from app.services.repository.metadata.metadata_builder import (
    count_total_files,
    find_main_entry_point,
    folder_structure,
)
from app.services.repository.parser.chunk_builder import CodeChunk

logger = logging.getLogger(__name__)

_MAX_CONTEXT_ITEMS = 30  # keep the enrichment prompt compact


class KnowledgeBuilder:
    def __init__(self, chat_model: Runnable[LanguageModelInput, BaseMessage] | None = None) -> None:
        self.chat_model = chat_model

    def build(
        self,
        *,
        repository_id: uuid.UUID,
        repo_path: Path,
        language: DetectorResult,
        framework: DetectorResult,
        dependency: DetectorResult,
        package_manager: DetectorResult,
        docker: DetectorResult,
        cuda: DetectorResult,
        security: DetectorResult,
        readme: DetectorResult,
        cicd: DetectorResult,
        deployment: DetectorResult,
        testing: DetectorResult,
        api_surface: DetectorResult,
        database: DetectorResult,
        quality: DetectorResult,
        chunks: list[CodeChunk],
        dependency_graph: dict[str, list[str]],
    ) -> RepositoryKnowledge:
        for result in (
            language, framework, dependency, package_manager, docker, cuda,
            security, readme, cicd, deployment, testing, api_surface, database, quality,
        ):
            for error in result.errors:
                logger.warning("detector %s reported an error: %s", result.detector_name, error)

        libraries = sorted(dependency.data.dependencies.keys())
        tree = folder_structure(repo_path)
        entry_point = find_main_entry_point(repo_path)
        enrichment = (
            self._enrich(language, framework, dependency, docker, cuda, security, tree, entry_point)
            if self.chat_model is not None
            else None
        )

        return RepositoryKnowledge(
            repository_id=repository_id,
            metadata=MetadataSection(
                name=readme.data.name,
                description=readme.data.description,
                repository_type=enrichment.repository_type if enrichment else None,
                license=readme.data.license,
                main_entry_point=entry_point,
                analyzed_at=datetime.now(timezone.utc),
            ),
            languages=LanguagesSection(
                languages=language.data.languages, stats=language.data.stats
            ),
            frameworks=FrameworksSection(frameworks=framework.data.frameworks),
            dependencies=DependenciesSection(
                dependencies=dependency.data.dependencies,
                package_managers=package_manager.data.package_managers,
                libraries=libraries,
            ),
            architecture=ArchitectureSection(
                summary=enrichment.architecture_summary if enrichment else None,
                folder_structure=tree,
                production_readiness=enrichment.production_readiness if enrichment else None,
                difficulty_level=enrichment.difficulty_level if enrichment else None,
                use_cases=enrichment.use_cases if enrichment else [],
                potential_applications=enrichment.potential_applications if enrichment else [],
            ),
            files=FilesSection(total_files=count_total_files(repo_path), folder_structure=tree),
            symbols=SymbolsSection(total_symbols=sum(1 for c in chunks if c.symbol_name)),
            imports=ImportsSection(dependency_graph=dependency_graph),
            apis=ApisSection(endpoints=api_surface.data.endpoints),
            databases=DatabasesSection(databases=database.data.databases, orms=database.data.orms),
            docker=DockerSection(
                docker_support=docker.data.docker_support,
                dockerfile_path=docker.data.dockerfile_path,
                compose_services=docker.data.compose_services,
            ),
            cuda=CudaSection(
                gpu_required=cuda.data.gpu_required, cuda_required=cuda.data.cuda_required
            ),
            cicd=CiCdSection(providers=cicd.data.providers, workflow_files=cicd.data.workflow_files),
            deployment=DeploymentSection(platforms=deployment.data.platforms),
            testing=TestingSection(
                frameworks=testing.data.frameworks,
                has_tests=testing.data.has_tests,
                test_file_count=testing.data.test_file_count,
            ),
            documentation=DocumentationSection(
                has_readme=readme.data.has_readme,
                installation_steps=readme.data.installation_steps,
                has_contributing=readme.data.has_contributing,
                has_license_file=readme.data.has_license_file,
            ),
            performance=PerformanceSection(notes=enrichment.performance_notes if enrichment else []),
            security=SecuritySection(findings=security.data.security_findings),
            quality=QualitySection(
                total_files=quality.data.total_files,
                total_lines=quality.data.total_lines,
                todo_count=quality.data.todo_count,
            ),
        )

    def _enrich(
        self,
        language: DetectorResult,
        framework: DetectorResult,
        dependency: DetectorResult,
        docker: DetectorResult,
        cuda: DetectorResult,
        security: DetectorResult,
        tree: dict,
        entry_point: str | None,
    ) -> KnowledgeEnrichment | None:
        try:
            chain = build_knowledge_enrichment_chain(self.chat_model)
            context = self._build_context(
                language, framework, dependency, docker, cuda, security, tree, entry_point
            )
            return chain.invoke({"context": context})
        except Exception:
            logger.warning(
                "Knowledge enrichment LLM call failed; leaving judgment fields empty",
                exc_info=True,
            )
            return None

    def _build_context(
        self,
        language: DetectorResult,
        framework: DetectorResult,
        dependency: DetectorResult,
        docker: DetectorResult,
        cuda: DetectorResult,
        security: DetectorResult,
        tree: dict,
        entry_point: str | None,
    ) -> str:
        deps = dependency.data.dependencies
        lines = [
            f"Languages: {', '.join(language.data.languages) or 'none detected'}",
            f"Frameworks: {', '.join(framework.data.frameworks) or 'none detected'}",
            "Notable dependencies: "
            + (", ".join(sorted(deps.keys())[:_MAX_CONTEXT_ITEMS]) or "none detected"),
            f"Docker support: {docker.data.docker_support}",
            f"GPU required: {cuda.data.gpu_required}, CUDA required: {cuda.data.cuda_required}",
            "Top-level structure: " + (", ".join(list(tree.keys())[:_MAX_CONTEXT_ITEMS]) or "unknown"),
            f"Main entry point: {entry_point or 'unknown'}",
            "Static security scan findings: "
            + ("; ".join(security.data.security_findings) or "none flagged"),
        ]
        return "\n".join(lines)
