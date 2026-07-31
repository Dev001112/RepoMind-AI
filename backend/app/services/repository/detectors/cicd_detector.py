"""Detects CI/CD provider configuration."""

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from app.services.repository.detectors.base import Detector

# (relative glob pattern, provider name). `.github/workflows` is a directory
# of files, everything else is a single well-known manifest name.
_SINGLE_FILE_PROVIDERS = [
    (".gitlab-ci.yml", "GitLab CI"),
    (".circleci/config.yml", "CircleCI"),
    ("Jenkinsfile", "Jenkins"),
    ("azure-pipelines.yml", "Azure Pipelines"),
    (".travis.yml", "Travis CI"),
]


class CiCdDetectionResult(BaseModel):
    providers: list[str] = []
    workflow_files: list[str] = []


class CiCdDetector(Detector[CiCdDetectionResult]):
    result_model: ClassVar[type[CiCdDetectionResult]] = CiCdDetectionResult

    def detect(self, repo_path: Path) -> CiCdDetectionResult:
        providers: list[str] = []
        workflow_files: list[str] = []

        workflows_dir = repo_path / ".github" / "workflows"
        if workflows_dir.is_dir():
            try:
                found = sorted(
                    p.name for p in workflows_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in (".yml", ".yaml")
                )
            except OSError:
                found = []
            if found:
                providers.append("GitHub Actions")
                workflow_files.extend(f".github/workflows/{name}" for name in found)

        for relative, provider in _SINGLE_FILE_PROVIDERS:
            if (repo_path / relative).is_file():
                providers.append(provider)
                workflow_files.append(relative)

        return CiCdDetectionResult(providers=providers, workflow_files=workflow_files)
