"""Detects Docker/container support. Phase 2 placeholder."""

from pathlib import Path

from app.services.repository.detectors.base import BaseDetector

_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist",
    "build", ".next", "target", "vendor", ".idea", ".vscode",
    ".pytest_cache", ".mypy_cache", ".tox",
}
_COMPOSE_NAMES = {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}


def _skip(name: str) -> bool:
    return name in _SKIP_DIRS or name.endswith(".egg-info")


def _has_docker_files(directory: Path) -> bool:
    try:
        entries = list(directory.iterdir())
    except OSError:
        return False
    for entry in entries:
        try:
            if not entry.is_file():
                continue
        except OSError:
            continue
        name_lower = entry.name.lower()
        if name_lower == "dockerfile" or name_lower.startswith("dockerfile."):
            return True
        if name_lower in _COMPOSE_NAMES:
            return True
    return False


class DockerDetector(BaseDetector):
    def __init__(self) -> None:
        pass

    def detect(self, repo_path: Path) -> dict:
        """Checks for Dockerfile / docker-compose.yml presence at the repo
        root or one level deep in an immediate subdirectory."""
        if not repo_path.is_dir():
            return {"docker_support": False}

        if _has_docker_files(repo_path):
            return {"docker_support": True}

        try:
            subdirs = [p for p in repo_path.iterdir() if p.is_dir()]
        except OSError:
            return {"docker_support": False}

        for subdir in subdirs:
            if _skip(subdir.name):
                continue
            if _has_docker_files(subdir):
                return {"docker_support": True}

        return {"docker_support": False}
