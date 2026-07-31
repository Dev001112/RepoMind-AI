"""Orchestrates the repository analysis pipeline: detectors -> parser ->
metadata -> knowledge_builder, against an already-cloned repo path.

Cloning happens before this runs (the caller already has a local repo_path);
persisting the result and embedding chunks happen after (the caller owns the
DB session and vector store) -- see app.services.repository.analysis_pipeline.
"""

import uuid
from pathlib import Path

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable

from app.models.schemas.knowledge import RepositoryKnowledge
from app.services.knowledge_builder.knowledge_builder import KnowledgeBuilder
from app.services.repository.detectors.cuda_detector import CudaDetector
from app.services.repository.detectors.dependency_detector import DependencyDetector
from app.services.repository.detectors.docker_detector import DockerDetector
from app.services.repository.detectors.framework_detector import FrameworkDetector
from app.services.repository.detectors.language_detector import LanguageDetector
from app.services.repository.detectors.package_manager_detector import (
    PackageManagerDetector,
)
from app.services.repository.detectors.security_detector import SecurityDetector
from app.services.repository.metadata.metadata_builder import MetadataBuilder
from app.services.repository.metadata.readme_parser import ReadmeParser
from app.services.repository.parser.chunk_builder import CodeChunk
from app.services.repository.parser.import_graph_builder import ImportGraphBuilder
from app.services.repository.parser.tree_sitter_parser import TreeSitterParser


class RepositoryScanner:
    """Runs detectors -> parser -> metadata -> knowledge_builder against an
    already-cloned repository."""

    def __init__(self, chat_model: Runnable[LanguageModelInput, BaseMessage] | None = None) -> None:
        self.language_detector = LanguageDetector()
        self.framework_detector = FrameworkDetector()
        self.dependency_detector = DependencyDetector()
        self.package_manager_detector = PackageManagerDetector()
        self.docker_detector = DockerDetector()
        self.cuda_detector = CudaDetector()
        self.security_detector = SecurityDetector()
        self.readme_parser = ReadmeParser()
        self.metadata_builder = MetadataBuilder()
        self.source_parser = TreeSitterParser()
        self.import_graph_builder = ImportGraphBuilder()
        self.knowledge_builder = KnowledgeBuilder(chat_model=chat_model)

    def scan(
        self, repository_id: uuid.UUID, repo_path: Path
    ) -> tuple[RepositoryKnowledge, list[CodeChunk]]:
        """Run the full analysis pipeline. Returns the assembled knowledge
        object plus the source chunks (for the caller to embed into Qdrant)."""
        languages = self.language_detector.detect(repo_path)
        frameworks = self.framework_detector.detect(repo_path)
        dependencies = self.dependency_detector.detect(repo_path)
        package_managers = self.package_manager_detector.detect(repo_path)
        docker = self.docker_detector.detect(repo_path)
        cuda = self.cuda_detector.detect(repo_path)
        security = self.security_detector.detect(repo_path)
        readme = self.readme_parser.parse(repo_path)
        chunks = self.source_parser.parse(repo_path)
        dependency_graph = self.import_graph_builder.build(repo_path)

        metadata = self.metadata_builder.build(
            repo_path,
            languages=languages,
            frameworks=frameworks,
            dependencies=dependencies,
            package_managers=package_managers,
            docker=docker,
            cuda=cuda,
            security=security,
            readme=readme,
            dependency_graph={"dependency_graph": dependency_graph},
        )
        knowledge = self.knowledge_builder.build(repository_id, metadata)
        return knowledge, chunks
