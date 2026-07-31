"""Interface for source parsers. Multiple language/tooling backends could
implement this (tree-sitter today, something else tomorrow), so an ABC is
warranted here.
"""

from abc import ABC, abstractmethod
from pathlib import Path

from app.services.repository.parser.chunk_builder import CodeChunk


class BaseSourceParser(ABC):
    @abstractmethod
    def parse(self, repo_path: Path) -> list[CodeChunk]:
        """Parse all source files under `repo_path` into CodeChunks."""
        raise NotImplementedError
