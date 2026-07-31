"""Interface for repository detectors. Each detector inspects a repo path
and reports one facet (language, framework, dependencies, ...). Multiple
interchangeable implementations exist, so an ABC is warranted here.
"""

from abc import ABC, abstractmethod
from pathlib import Path


class BaseDetector(ABC):
    @abstractmethod
    def detect(self, repo_path: Path) -> dict:
        """Inspect `repo_path` and return this detector's findings."""
        raise NotImplementedError
