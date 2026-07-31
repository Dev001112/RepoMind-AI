"""Cheap repo-size/hygiene heuristics -- NOT a real static-analysis quality
score (no complexity/maintainability metrics). Deeper quality scoring is
future work if it's ever wanted; this is deliberately just counts."""

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from app.services.repository.detectors.base import Detector
from app.utils.file_utils import SKIP_DIRS

_SOURCE_EXTS = {
    ".py", ".js", ".jsx", ".mjs", ".ts", ".tsx", ".go", ".rs", ".java", ".c", ".h",
    ".cpp", ".hpp", ".cc", ".rb", ".php", ".cs",
}
_MAX_FILE_SIZE = 1 * 1024 * 1024
_MAX_FILES_SCANNED = 3000
_TODO_MARKERS = ("TODO", "FIXME")


class QualityDetectionResult(BaseModel):
    total_files: int = 0
    total_lines: int = 0
    todo_count: int = 0


class QualityDetector(Detector[QualityDetectionResult]):
    result_model: ClassVar[type[QualityDetectionResult]] = QualityDetectionResult

    def detect(self, repo_path: Path) -> QualityDetectionResult:
        total_files = 0
        total_lines = 0
        todo_count = 0
        scanned = 0

        try:
            for dirpath, dirnames, filenames in Path(repo_path).walk():
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                for filename in filenames:
                    if Path(filename).suffix.lower() not in _SOURCE_EXTS:
                        continue
                    total_files += 1
                    if scanned >= _MAX_FILES_SCANNED:
                        continue
                    file_path = dirpath / filename
                    try:
                        if file_path.stat().st_size > _MAX_FILE_SIZE:
                            continue
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        continue
                    scanned += 1
                    total_lines += len(content.splitlines())
                    todo_count += sum(content.count(marker) for marker in _TODO_MARKERS)
        except OSError:
            pass

        return QualityDetectionResult(
            total_files=total_files, total_lines=total_lines, todo_count=todo_count
        )
