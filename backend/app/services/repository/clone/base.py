"""Interface for anything that can materialize a repository onto local disk.

Multiple interchangeable implementations exist (git clone, zip extraction),
so an ABC is warranted here.
"""

from abc import ABC, abstractmethod
from pathlib import Path


class BaseCloner(ABC):
    @abstractmethod
    def clone(self, source: str, dest: Path) -> Path:
        """Materialize `source` under `dest` and return the resulting path."""
        raise NotImplementedError
