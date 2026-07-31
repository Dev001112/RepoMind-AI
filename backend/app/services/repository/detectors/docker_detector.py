"""Detects Docker/container support."""

import re
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from app.services.repository.detectors.base import Detector

_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist",
    "build", ".next", "target", "vendor", ".idea", ".vscode",
    ".pytest_cache", ".mypy_cache", ".tox",
}
_COMPOSE_NAMES = {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}
# One `services:` top-level key followed by indented `  name:` children -- good
# enough to list service names without a YAML parser (no PyYAML in this
# project; a real multi-document/anchor-heavy compose file could confuse this,
# which is an acceptable heuristic-level trade-off for "what services exist").
_SERVICES_KEY_RE = re.compile(r"^services:\s*$")
_SERVICE_NAME_RE = re.compile(r"^(\s+)([A-Za-z0-9_.\-]+):\s*$")


def _skip(name: str) -> bool:
    return name in _SKIP_DIRS or name.endswith(".egg-info")


def _find_docker_files(directory: Path) -> tuple[str | None, str | None]:
    """Returns (dockerfile_path, compose_path) relative-name pair, either may be None."""
    try:
        entries = list(directory.iterdir())
    except OSError:
        return None, None
    dockerfile = None
    compose = None
    for entry in entries:
        try:
            if not entry.is_file():
                continue
        except OSError:
            continue
        name_lower = entry.name.lower()
        if dockerfile is None and (name_lower == "dockerfile" or name_lower.startswith("dockerfile.")):
            dockerfile = entry.name
        if compose is None and name_lower in _COMPOSE_NAMES:
            compose = entry.name
    return dockerfile, compose


def _compose_service_names(compose_path: Path) -> list[str]:
    try:
        text = compose_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    lines = text.splitlines()
    services: list[str] = []
    in_services = False
    services_indent: str | None = None
    for line in lines:
        if _SERVICES_KEY_RE.match(line):
            in_services = True
            continue
        if not in_services:
            continue
        match = _SERVICE_NAME_RE.match(line)
        if match is None:
            if line.strip() and not line.startswith(" "):
                break  # dedented back to top level -- services block ended
            continue
        indent = match.group(1)
        if services_indent is None:
            services_indent = indent
        if indent != services_indent:
            continue  # a nested key under a service, not a service name itself
        services.append(match.group(2))
    return services


class DockerDetectionResult(BaseModel):
    docker_support: bool = False
    dockerfile_path: str | None = None
    compose_services: list[str] = []


class DockerDetector(Detector[DockerDetectionResult]):
    result_model: ClassVar[type[DockerDetectionResult]] = DockerDetectionResult

    def detect(self, repo_path: Path) -> DockerDetectionResult:
        """Checks for Dockerfile / docker-compose.yml presence at the repo
        root or one level deep in an immediate subdirectory."""
        if not repo_path.is_dir():
            return DockerDetectionResult()

        dockerfile, compose = _find_docker_files(repo_path)
        if dockerfile is None and compose is None:
            try:
                subdirs = [p for p in repo_path.iterdir() if p.is_dir()]
            except OSError:
                subdirs = []
            for subdir in subdirs:
                if _skip(subdir.name):
                    continue
                dockerfile, compose = _find_docker_files(subdir)
                if dockerfile is not None or compose is not None:
                    repo_path = subdir
                    break

        if dockerfile is None and compose is None:
            return DockerDetectionResult()

        services = _compose_service_names(repo_path / compose) if compose else []
        return DockerDetectionResult(
            docker_support=True,
            dockerfile_path=dockerfile,
            compose_services=services,
        )
