from pathlib import Path

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
from app.services.knowledge_builder.knowledge_builder import KnowledgeBuilder

import uuid


def _build_sample_repo(tmp_path: Path) -> Path:
    (tmp_path / "requirements.txt").write_text("flask==3.0.0\npytest==8.0.0\n")
    (tmp_path / "README.md").write_text("# Sample\n\nA sample Flask app.\n")
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\n")
    (tmp_path / "app.py").write_text("def main():\n    pass\n")
    return tmp_path


def _run_all_detectors(repo_path: Path) -> dict:
    return {
        "language": LanguageDetector().run(repo_path),
        "framework": FrameworkDetector().run(repo_path),
        "dependency": DependencyDetector().run(repo_path),
        "package_manager": PackageManagerDetector().run(repo_path),
        "docker": DockerDetector().run(repo_path),
        "cuda": CudaDetector().run(repo_path),
        "security": SecurityDetector().run(repo_path),
        "readme": ReadmeParser().run(repo_path),
        "cicd": CiCdDetector().run(repo_path),
        "deployment": DeploymentDetector().run(repo_path),
        "testing": TestingDetector().run(repo_path),
        "api_surface": ApiSurfaceDetector().run(repo_path),
        "database": DatabaseDetector().run(repo_path),
        "quality": QualityDetector().run(repo_path),
    }


def test_build_assembles_every_section_without_an_llm(tmp_path: Path) -> None:
    repo_path = _build_sample_repo(tmp_path)
    results = _run_all_detectors(repo_path)
    chunks = [
        CodeChunk(file_path="app.py", content="def main(): pass", start_line=1, end_line=1,
                  language="python", symbol_name="main"),
        CodeChunk(file_path="app.py", content="# module docstring", start_line=1, end_line=1,
                  language="python", symbol_name=None),
    ]

    knowledge = KnowledgeBuilder(chat_model=None).build(
        repository_id=uuid.uuid4(),
        repo_path=repo_path,
        chunks=chunks,
        dependency_graph={"app.py": []},
        **results,
    )

    assert knowledge.metadata.name == "Sample"
    assert "Flask" in knowledge.frameworks.frameworks
    assert knowledge.dependencies.dependencies["flask"] == "==3.0.0"
    assert knowledge.docker.docker_support is True
    assert knowledge.testing.frameworks == ["pytest"]
    # No chat_model configured -- judgment fields stay empty, not fabricated.
    assert knowledge.architecture.summary is None
    assert knowledge.architecture.production_readiness is None
    # Deterministic sections still assemble even without LLM enrichment.
    assert knowledge.symbols.total_symbols == 1
    assert knowledge.imports.dependency_graph == {"app.py": []}


def test_detector_errors_are_logged_not_fatal(tmp_path: Path, caplog) -> None:
    repo_path = _build_sample_repo(tmp_path)
    results = _run_all_detectors(repo_path)
    # Simulate a detector that failed -- build() must still assemble successfully.
    results["security"].errors.append("simulated failure")

    with caplog.at_level("WARNING"):
        knowledge = KnowledgeBuilder(chat_model=None).build(
            repository_id=uuid.uuid4(),
            repo_path=repo_path,
            chunks=[],
            dependency_graph={},
            **results,
        )

    assert knowledge is not None
    assert any("simulated failure" in record.message for record in caplog.records)
