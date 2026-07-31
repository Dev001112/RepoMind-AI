"""Detects declared dependencies."""
import json
import re
import tomllib
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from app.services.repository.detectors.base import Detector

# Matches "name==1.2.3", "name>=1.2", "name~=1.0", "name[extra]>=1.0", or bare "name".
_REQ_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*(?:\[[^\]]*\])?\s*(.*?)\s*$")


def _parse_requirement_line(line: str) -> tuple[str, str] | None:
    match = _REQ_RE.match(line)
    if not match:
        return None
    name = match.group(1).strip()
    if not name:
        return None
    specifier = match.group(2).strip()
    return name, (specifier if specifier else "*")


def _parse_requirements_txt(repo_path: Path, deps: dict[str, str]) -> None:
    path = repo_path / "requirements.txt"
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        parsed = _parse_requirement_line(line)
        if parsed is None:
            continue
        name, specifier = parsed
        deps.setdefault(name, specifier)


def _parse_pyproject_toml(repo_path: Path, deps: dict[str, str]) -> None:
    path = repo_path / "pyproject.toml"
    if not path.is_file():
        return
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return

    for req in data.get("project", {}).get("dependencies", []) or []:
        if not isinstance(req, str):
            continue
        parsed = _parse_requirement_line(req)
        if parsed is None:
            continue
        name, specifier = parsed
        deps.setdefault(name, specifier)

    poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {}) or {}
    for name, spec in poetry_deps.items():
        if name == "python":
            continue
        if isinstance(spec, str):
            deps.setdefault(name, spec if spec else "*")
        elif isinstance(spec, dict):
            deps.setdefault(name, spec.get("version") or "*")
        else:
            deps.setdefault(name, "*")


def _parse_package_json(repo_path: Path, deps: dict[str, str]) -> None:
    path = repo_path / "package.json"
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return
    if not isinstance(data, dict):
        return
    for key in ("dependencies", "devDependencies"):
        section = data.get(key) or {}
        if not isinstance(section, dict):
            continue
        for name, version in section.items():
            deps.setdefault(name, version if isinstance(version, str) else "*")


def _parse_go_mod(repo_path: Path, deps: dict[str, str]) -> None:
    path = repo_path / "go.mod"
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    in_block = False
    for raw_line in text.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if not line:
            continue
        if line.startswith("require") and line.endswith("("):
            in_block = True
            continue
        if in_block and line == ")":
            in_block = False
            continue
        if line.startswith("require"):
            line = line[len("require"):].strip()
        elif not in_block:
            continue
        parts = line.split()
        if len(parts) >= 2:
            name, version = parts[0], parts[1]
            deps.setdefault(name, version)


def _parse_cargo_toml(repo_path: Path, deps: dict[str, str]) -> None:
    path = repo_path / "Cargo.toml"
    if not path.is_file():
        return
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return
    for name, spec in (data.get("dependencies", {}) or {}).items():
        if isinstance(spec, str):
            deps.setdefault(name, spec if spec else "*")
        elif isinstance(spec, dict):
            deps.setdefault(name, spec.get("version") or "*")
        else:
            deps.setdefault(name, "*")


class DependencyDetectionResult(BaseModel):
    dependencies: dict[str, str] = {}


class DependencyDetector(Detector[DependencyDetectionResult]):
    result_model: ClassVar[type[DependencyDetectionResult]] = DependencyDetectionResult

    def detect(self, repo_path: Path) -> DependencyDetectionResult:
        """Parses manifests (requirements.txt, pyproject.toml, package.json,
        go.mod, Cargo.toml) into a name->version-constraint map."""
        deps: dict[str, str] = {}
        for parser in (
            _parse_requirements_txt,
            _parse_pyproject_toml,
            _parse_package_json,
            _parse_go_mod,
            _parse_cargo_toml,
        ):
            try:
                parser(repo_path, deps)
            except Exception:
                continue
        return DependencyDetectionResult(dependencies=deps)
