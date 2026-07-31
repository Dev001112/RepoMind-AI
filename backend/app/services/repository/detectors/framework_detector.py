"""Detects frameworks in use (Django, FastAPI, React, ...)."""

import json
import tomllib
from pathlib import Path

from app.services.repository.detectors.base import BaseDetector

# (substring to search for, framework name). Checked in manifest-scan order;
# first match per name wins, duplicates are skipped.
PY_SIGNATURES = [
    ("django", "Django"),
    ("flask", "Flask"),
    ("fastapi", "FastAPI"),
    ("streamlit", "Streamlit"),
    ("pytorch", "PyTorch"),
    ("torch", "PyTorch"),
    ("tensorflow", "TensorFlow"),
    ("transformers", "Transformers"),
    ("celery", "Celery"),
    ("sqlalchemy", "SQLAlchemy"),
    ("pydantic", "Pydantic"),
    ("scrapy", "Scrapy"),
]

JS_SIGNATURES = [
    ("react", "React"),
    ("next", "Next.js"),
    ("vue", "Vue"),
    ("@angular/core", "Angular"),
    ("express", "Express"),
    ("svelte", "Svelte"),
    ("@nestjs/core", "NestJS"),
    ("vite", "Vite"),
    ("tailwindcss", "Tailwind CSS"),
]

GO_SIGNATURES = [
    ("gin-gonic", "Gin"),
    ("labstack/echo", "Echo"),
    ("gofiber/fiber", "Fiber"),
]

RUST_SIGNATURES = [
    ("actix-web", "Actix"),
    ("rocket", "Rocket"),
    ("axum", "Axum"),
]


def _match(text: str, signatures: list[tuple[str, str]], found: list[str]) -> None:
    text = text.lower()
    for needle, name in signatures:
        if needle in text and name not in found:
            found.append(name)


class FrameworkDetector(BaseDetector):
    def __init__(self) -> None:
        pass

    def detect(self, repo_path: Path) -> dict:
        found: list[str] = []

        for filename in ("requirements.txt", "Pipfile"):
            path = repo_path / filename
            if path.is_file():
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                _match(text, PY_SIGNATURES, found)

        pyproject = repo_path / "pyproject.toml"
        if pyproject.is_file():
            data = None
            try:
                with pyproject.open("rb") as f:
                    data = tomllib.load(f)
            except (OSError, tomllib.TOMLDecodeError):
                data = None
            if data:
                deps = data.get("project", {}).get("dependencies", [])
                poetry_deps = (
                    data.get("tool", {}).get("poetry", {}).get("dependencies", {})
                )
                text = " ".join(str(d) for d in deps) + " " + " ".join(poetry_deps.keys())
                _match(text, PY_SIGNATURES, found)

        package_json = repo_path / "package.json"
        if package_json.is_file():
            data = None
            try:
                data = json.loads(package_json.read_text(encoding="utf-8", errors="ignore"))
            except (OSError, json.JSONDecodeError):
                data = None
            if isinstance(data, dict):
                keys = list(data.get("dependencies", {}) or {}) + list(
                    data.get("devDependencies", {}) or {}
                )
                _match(" ".join(keys), JS_SIGNATURES, found)

        go_mod = repo_path / "go.mod"
        if go_mod.is_file():
            try:
                text = go_mod.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                text = ""
            _match(text, GO_SIGNATURES, found)

        cargo_toml = repo_path / "Cargo.toml"
        if cargo_toml.is_file():
            try:
                text = cargo_toml.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                text = ""
            _match(text, RUST_SIGNATURES, found)

        return {"frameworks": found}
