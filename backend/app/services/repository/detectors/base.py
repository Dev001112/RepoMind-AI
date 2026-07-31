"""Interface for repository detectors. Each detector inspects a repo path
and reports one facet (language, framework, dependencies, ...) as a typed,
versioned, confidence-scored result -- so every consumer downstream (the
Knowledge Builder, logs, future re-analysis diffing) can reason about
provenance and failure without re-deriving it from a bare dict.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class DetectorResult(BaseModel, Generic[T]):
    detector_name: str
    detector_version: str
    data: T
    # 1.0 = deterministic certainty (file presence, manifest parse). Lower for
    # heuristic signals (e.g. a README license guess, a route-regex scan) --
    # see each detector's `confidence()` override.
    confidence: float = 1.0
    detected_at: datetime
    errors: list[str] = []
    warnings: list[str] = []


class Detector(ABC, Generic[T]):
    """Subclasses implement `detect()` with their existing logic returning a
    typed Pydantic model instead of a dict. `run()` is the only thing callers
    invoke -- it wraps the result (or a safe default + captured error, if
    `detect()` raises) in a `DetectorResult` envelope."""

    version: ClassVar[str] = "1"
    result_model: ClassVar[type[BaseModel]]

    @abstractmethod
    def detect(self, repo_path: Path) -> T:
        """Inspect `repo_path` and return this detector's typed findings."""
        raise NotImplementedError

    def confidence(self, data: T) -> float:
        """Override for detectors whose signal is inherently heuristic."""
        return 1.0

    def run(self, repo_path: Path) -> DetectorResult[T]:
        errors: list[str] = []
        try:
            data = self.detect(repo_path)
        except Exception as exc:
            errors.append(str(exc))
            data = self.result_model()
        return DetectorResult(
            detector_name=type(self).__name__,
            detector_version=self.version,
            data=data,
            confidence=self.confidence(data),
            detected_at=datetime.now(timezone.utc),
            errors=errors,
        )
