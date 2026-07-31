"""Detects which package manager(s) the repo uses."""

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from app.services.repository.detectors.base import Detector


class PackageManagerDetectionResult(BaseModel):
    package_managers: list[str] = []


class PackageManagerDetector(Detector[PackageManagerDetectionResult]):
    result_model: ClassVar[type[PackageManagerDetectionResult]] = PackageManagerDetectionResult

    def detect(self, repo_path: Path) -> PackageManagerDetectionResult:
        """Check for presence of lockfile/manifest markers at the repo root."""
        managers: list[str] = []

        # requirements.txt only counts as "pip" if none of these are present,
        # since requirements.txt often coexists with a poetry/uv export.
        has_poetry = (repo_path / "poetry.lock").exists()
        has_uv = (repo_path / "uv.lock").exists()
        has_pipenv = (repo_path / "Pipfile.lock").exists() or (repo_path / "Pipfile").exists()

        if has_poetry:
            managers.append("poetry")
        if has_uv:
            managers.append("uv")
        if has_pipenv:
            managers.append("pipenv")
        if not (has_poetry or has_uv or has_pipenv) and (repo_path / "requirements.txt").exists():
            managers.append("pip")
        if (repo_path / "package-lock.json").exists():
            managers.append("npm")
        if (repo_path / "yarn.lock").exists():
            managers.append("yarn")
        if (repo_path / "pnpm-lock.yaml").exists():
            managers.append("pnpm")
        if (repo_path / "Cargo.lock").exists():
            managers.append("cargo")
        if (repo_path / "go.sum").exists() or (repo_path / "go.mod").exists():
            managers.append("go modules")
        if (repo_path / "Gemfile.lock").exists():
            managers.append("bundler")
        if (repo_path / "composer.lock").exists():
            managers.append("composer")

        return PackageManagerDetectionResult(package_managers=managers)
