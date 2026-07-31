"""Detects deployment-platform configuration (file-presence only, no
Dockerfile/compose parsing -- DockerDetector already owns that facet)."""

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from app.services.repository.detectors.base import Detector

_MARKER_FILES = [
    ("Procfile", "Heroku"),
    ("vercel.json", "Vercel"),
    ("netlify.toml", "Netlify"),
    ("render.yaml", "Render"),
    ("fly.toml", "Fly.io"),
    ("app.yaml", "Google App Engine"),
]
_MARKER_DIRS = [
    ("k8s", "Kubernetes"),
    ("kubernetes", "Kubernetes"),
]


class DeploymentDetectionResult(BaseModel):
    platforms: list[str] = []


class DeploymentDetector(Detector[DeploymentDetectionResult]):
    result_model: ClassVar[type[DeploymentDetectionResult]] = DeploymentDetectionResult

    def detect(self, repo_path: Path) -> DeploymentDetectionResult:
        platforms: list[str] = []

        for filename, platform in _MARKER_FILES:
            if (repo_path / filename).is_file() and platform not in platforms:
                platforms.append(platform)

        for dirname, platform in _MARKER_DIRS:
            if (repo_path / dirname).is_dir() and platform not in platforms:
                platforms.append(platform)

        return DeploymentDetectionResult(platforms=platforms)
