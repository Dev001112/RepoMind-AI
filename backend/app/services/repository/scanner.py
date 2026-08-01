"""Orchestrates the repository analysis pipeline: detectors -> parser ->
knowledge_builder, against an already-cloned repo path.

Cloning happens before this runs (the caller already has a local repo_path);
persisting the result and embedding chunks happen after (the caller owns the
DB session and vector store) -- see app.services.repository.pipeline.stages.
The scanner stays DB-agnostic: it returns the typed `DetectorResult`s so the
caller can persist them, and it reports per-detector lifecycle through an
optional `DetectorSink` (the event log) without knowing how it's stored.
"""

import uuid
from pathlib import Path
from typing import Protocol

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable

from app.models.schemas.knowledge import RepositoryKnowledge
from app.services.knowledge_builder.knowledge_builder import KnowledgeBuilder
from app.services.repository.detectors.api_surface_detector import ApiSurfaceDetector
from app.services.repository.detectors.base import Detector, DetectorResult
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


class DetectorSink(Protocol):
    """Per-detector lifecycle callback the scanning stage implements (it
    appends to the analysis event log); the scanner only calls it."""

    def started(self, detector_name: str) -> None: ...

    def completed(
        self,
        detector_name: str,
        duration_ms: int,
        errors: list[str],
        warnings: list[str],
    ) -> None: ...


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
        self.detectors: list[Detector] = [
            self.language_detector,
            self.framework_detector,
            self.dependency_detector,
            self.package_manager_detector,
            self.docker_detector,
            self.cuda_detector,
            self.security_detector,
            self.readme_parser,
            self.cicd_detector,
            self.deployment_detector,
            self.testing_detector,
            self.api_surface_detector,
            self.database_detector,
            self.quality_detector,
        ]

    def scan(
        self,
        repository_id: uuid.UUID,
        repo_path: Path,
        sink: DetectorSink | None = None,
    ) -> tuple[RepositoryKnowledge, list[CodeChunk], list[DetectorResult]]:
        """Run the full analysis pipeline. Returns the assembled knowledge
        object, the source chunks (for the caller to embed into Qdrant), and
        the raw typed detector results (for the caller to persist)."""
        results: list[DetectorResult] = []

        def run_detector(detector: Detector) -> DetectorResult:
            name = detector.__class__.__name__
            if sink is not None:
                sink.started(name)
            result = detector.run(repo_path)
            results.append(result)
            if sink is not None:
                sink.completed(
                    name,
                    result.duration_ms,
                    result.errors,
                    result.warnings,
                )
            return result

        language = run_detector(self.detectors[0])
        framework = run_detector(self.detectors[1])
        dependency = run_detector(self.detectors[2])
        package_manager = run_detector(self.detectors[3])
        docker = run_detector(self.detectors[4])
        cuda = run_detector(self.detectors[5])
        security = run_detector(self.detectors[6])
        readme = run_detector(self.detectors[7])
        cicd = run_detector(self.detectors[8])
        deployment = run_detector(self.detectors[9])
        testing = run_detector(self.detectors[10])
        api_surface = run_detector(self.detectors[11])
        database = run_detector(self.detectors[12])
        quality = run_detector(self.detectors[13])

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
        return knowledge, chunks, results
