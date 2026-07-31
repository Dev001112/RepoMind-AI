"""Detects test frameworks in use and whether the repo has a test suite at all."""

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from app.services.repository.detectors.base import Detector
from app.utils.file_utils import SKIP_DIRS

_MANIFEST_NAMES = ("requirements.txt", "pyproject.toml", "package.json", "Pipfile", "go.mod")
# (substring to search for in manifest text, framework name).
_SIGNATURES = [
    ("pytest", "pytest"),
    ("unittest", "unittest"),
    ("jest", "Jest"),
    ("mocha", "Mocha"),
    ("vitest", "Vitest"),
    ("junit", "JUnit"),
    ("rspec", "RSpec"),
    ("testing/testify", "testify"),
]
_TEST_DIR_NAMES = {"tests", "test", "__tests__", "spec", "specs"}
_MAX_DEPTH = 3


class TestingDetectionResult(BaseModel):
    frameworks: list[str] = []
    has_tests: bool = False
    test_file_count: int = 0


class TestingDetector(Detector[TestingDetectionResult]):
    result_model: ClassVar[type[TestingDetectionResult]] = TestingDetectionResult

    def detect(self, repo_path: Path) -> TestingDetectionResult:
        frameworks: list[str] = []
        for name in _MANIFEST_NAMES:
            path = repo_path / name
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore").lower()
            except OSError:
                continue
            for needle, framework in _SIGNATURES:
                if needle in text and framework not in frameworks:
                    frameworks.append(framework)

        test_file_count = 0
        try:
            for root, dirnames, filenames in repo_path.walk():
                depth = len(Path(root).relative_to(repo_path).parts)
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                if depth > _MAX_DEPTH:
                    dirnames[:] = []
                    continue
                if Path(root).name in _TEST_DIR_NAMES:
                    test_file_count += len(filenames)
        except OSError:
            pass

        return TestingDetectionResult(
            frameworks=frameworks,
            has_tests=bool(frameworks) or test_file_count > 0,
            test_file_count=test_file_count,
        )
