"""Detects programming languages used in the repository."""

from collections import Counter
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from app.models.schemas.knowledge import LanguageStat
from app.services.repository.detectors.base import Detector

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist",
    "build", ".next", "target", "vendor", ".idea", ".vscode", ".pytest_cache",
    ".mypy_cache", ".tox",
}

EXTENSION_LANGUAGES = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".hpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".scala": "Scala",
    ".sh": "Shell",
    ".bash": "Shell",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sql": "SQL",
    ".m": "Objective-C",
    ".lua": "Lua",
    ".dart": "Dart",
    ".r": "R",
    ".pl": "Perl",
}


class LanguageDetectionResult(BaseModel):
    languages: list[str] = []
    stats: list[LanguageStat] = []


class LanguageDetector(Detector[LanguageDetectionResult]):
    result_model: ClassVar[type[LanguageDetectionResult]] = LanguageDetectionResult

    def detect(self, repo_path: Path) -> LanguageDetectionResult:
        """Count files by extension and rank languages by prevalence."""
        counts: Counter[str] = Counter()

        repo_path = Path(repo_path)
        if not repo_path.is_dir():
            return LanguageDetectionResult()

        for root, dirnames, filenames in repo_path.walk():
            dirnames[:] = [
                d for d in dirnames
                if d not in SKIP_DIRS and not d.endswith(".egg-info")
            ]
            for filename in filenames:
                language = EXTENSION_LANGUAGES.get(Path(filename).suffix.lower())
                if language:
                    counts[language] += 1

        ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
        return LanguageDetectionResult(
            languages=[language for language, _ in ranked],
            stats=[LanguageStat(name=name, file_count=count) for name, count in ranked],
        )
