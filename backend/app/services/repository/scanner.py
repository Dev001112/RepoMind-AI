"""Orchestrates the repository analysis pipeline: detectors -> parser ->
knowledge_builder, against an already-cloned repo path.

Cloning happens before this runs (the caller already has a local repo_path);
persisting the result and embedding chunks happen after (the caller owns the
DB session and vector store) -- see app.services.repository.pipeline.stages.
"""

import uuid
from pathlib import Path

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable

from app.models.schemas.knowledge import RepositoryKnowledge
from app.services.knowledge_builder.knowledge_builder import KnowledgeBuilder
from app.services.repository.detectors.api_surface_detector import ApiSurfaceDetector
from app.services.repository.detectors.cicd_detector import CiCdDetector
from app.services.repository.detectors.cuda_detector import CudaDetector
from app.services.repository.detectors.database_detector import DatabaseDetector
from app.services.repository.detectors.dependency_detector import DependencyDetector
from app.services.repository.detectors.deployment_detector import DeploymentDetector
from app.services.repository.detectors.docker_detector import DockerDetector
from app.services.repository.detectors.framework_detector import FrameworkDetector
from app.services.repository.detectors.language_detector import LanguageDetector
from app.services.repository.detectors.package_manager_detector import (
    PackageManagerDetector,
)
from app.services.repository.detectors.quality_detector import QualityDetector
from app.services.repository.detectors.security_detector import SecurityDetector
from app.services.repository.detectors.testing_detector import TestingDetector
from app.services.repository.metadata.readme_parser import ReadmeParser
from app.services.repository.parser.chunk_builder import CodeChunk
from app.services.repository.parser.import_graph_builder import ImportGraphBuilder
from app.services.repository.parser.tree_sitter_parser import TreeSitterParser


class RepositoryScanner:
    """Runs every detector plus the tree-sitter/import-graph parsers against
    an already-cloned repository, then hands their typed results to the
    Knowledge Builder for assembly into the canonical RepositoryKnowledge."""

    def __init__(self, chat_model: Runnable[LanguageModelInput, BaseMessage] | None = None) -> None:
        self.language_detector = LanguageDetector()
        self.framework_detector = FrameworkDetector()
        self.dependency_detector = DependencyDetector()
        self.package_manager_detector = PackageManagerDetector()
        self.docker_detector = DockerDetector()
        self.cuda_detector = CudaDetector()
        self.security_detector = SecurityDetector()
        self.readme_parser = ReadmeParser()
        self.cicd_detector = CiCdDetector()
        self.deployment_detector = DeploymentDetector()
        self.testing_detector = TestingDetector()
        self.api_surface_detector = ApiSurfaceDetector()
        self.database_detector = DatabaseDetector()
        self.quality_detector = QualityDetector()
        self.source_parser = TreeSitterParser()
        self.import_graph_builder = ImportGraphBuilder()
        self.knowledge_builder = KnowledgeBuilder(chat_model=chat_model)

    def scan(
        self, repository_id: uuid.UUID, repo_path: Path
    ) -> tuple[RepositoryKnowledge, list[CodeChunk]]:
        """Run the full analysis pipeline. Returns the assembled knowledge
        object plus the source chunks (for the caller to embed into Qdrant)."""
        language = self.language_detector.run(repo_path)
        framework = self.framework_detector.run(repo_path)
        dependency = self.dependency_detector.run(repo_path)
        package_manager = self.package_manager_detector.run(repo_path)
        docker = self.docker_detector.run(repo_path)
        cuda = self.cuda_detector.run(repo_path)
        security = self.security_detector.run(repo_path)
        readme = self.readme_parser.run(repo_path)
        cicd = self.cicd_detector.run(repo_path)
        deployment = self.deployment_detector.run(repo_path)
        testing = self.testing_detector.run(repo_path)
        api_surface = self.api_surface_detector.run(repo_path)
        database = self.database_detector.run(repo_path)
        quality = self.quality_detector.run(repo_path)

        chunks = self.source_parser.parse(repo_path)
        dependency_graph = self.import_graph_builder.build(repo_path)

        knowledge = self.knowledge_builder.build(
            repository_id=repository_id,
            repo_path=repo_path,
            language=language,
            framework=framework,
            dependency=dependency,
            package_manager=package_manager,
            docker=docker,
            cuda=cuda,
            security=security,
            readme=readme,
            cicd=cicd,
            deployment=deployment,
            testing=testing,
            api_surface=api_surface,
            database=database,
            quality=quality,
            chunks=chunks,
            dependency_graph=dependency_graph,
        )
        return knowledge, chunks
