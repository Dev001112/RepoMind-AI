"""Parses source files with tree-sitter grammars, falling back to plain-text
line-window chunking for languages tree-sitter doesn't cover (or fails on).
"""

import logging
from pathlib import Path

from app.services.repository.parser.base import BaseSourceParser
from app.services.repository.parser.chunk_builder import ChunkBuilder, CodeChunk, ParsedFile

logger = logging.getLogger(__name__)

_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist", "build",
    ".next", "target", "vendor", ".idea", ".vscode", ".pytest_cache", ".mypy_cache",
    ".tox",
}

# tree_sitter_languages grammar name per extension. Grammar-load or parse failure
# falls back to line-window chunking (see parse()), not an error.
_LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "c_sharp",
}

# No tree-sitter grammar for these -- always line-window chunked, but still worth
# embedding for RAG (docs, config, CI). Without this, a huge fraction of a typical
# repo (README, docs/, package.json, Dockerfile, CI yaml) would silently never be
# chunked at all rather than actually falling back, despite that being the intent.
_TEXT_ONLY_EXTENSIONS = {
    ".md", ".rst", ".txt", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".xml",
}
_TEXT_ONLY_FILENAMES = {"dockerfile", "makefile", "readme", "license", "changelog"}

_MAX_FILE_BYTES = 500_000  # skip anything larger; unlikely to be hand-written source
_MAX_FILES_SCANNED = 1000  # repo-wide cap so a huge repo can't stall the pipeline
_MAX_CANDIDATES_CONSIDERED = 5000  # bound the "gather to sort" pass for pathological repos

# rglob() yields files in whatever order the filesystem happens to return, with no
# regard for importance. A repo with an extensive test suite (Flask's has 30+ test
# files) can exhaust MAX_FILES_SCANNED / ChunkBuilder's MAX_CHUNKS on tests/docs
# before ever reaching the actual library code under src/ -- for a tool whose whole
# point is understanding a repo's real implementation, that's exactly backwards.
# De-prioritizing (not excluding) these directories fixes it.
_LOW_PRIORITY_DIR_MARKERS = {
    "test", "tests", "__tests__", "spec", "specs", "docs", "doc", "examples",
    "example", "fixtures",
}


def _priority(path: Path, repo_path: Path) -> tuple[int, str]:
    dir_parts = {part.lower() for part in path.relative_to(repo_path).parts[:-1]}
    is_low_priority = 1 if dir_parts & _LOW_PRIORITY_DIR_MARKERS else 0
    return (is_low_priority, str(path))


def _detect_language(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in _LANGUAGE_BY_EXTENSION:
        return _LANGUAGE_BY_EXTENSION[suffix]
    if suffix in _TEXT_ONLY_EXTENSIONS:
        return "text"
    if not suffix and path.name.lower() in _TEXT_ONLY_FILENAMES:
        return "text"
    return None


class TreeSitterParser(BaseSourceParser):
    def __init__(self) -> None:
        self.chunk_builder = ChunkBuilder()
        self._parser_cache: dict[str, object] = {}

    def _get_parser(self, language: str):
        """Lazily load and cache a tree-sitter parser per language; None if unavailable."""
        if language in self._parser_cache:
            return self._parser_cache[language]

        parser = None
        try:
            from tree_sitter_languages import get_parser

            parser = get_parser(language)
        except Exception:
            parser = None
        self._parser_cache[language] = parser
        return parser

    def _iter_source_files(self, repo_path: Path):
        candidates: list[Path] = []
        for path in repo_path.rglob("*"):
            if len(candidates) >= _MAX_CANDIDATES_CONSIDERED:
                break
            if path.is_symlink():
                # A cloned repo's symlink can point anywhere on disk (e.g. /etc/passwd) --
                # following it would read and embed arbitrary host files into the chunk set.
                continue
            if not path.is_file():
                continue
            if any(part in _SKIP_DIRS for part in path.relative_to(repo_path).parts):
                continue
            if _detect_language(path) is None:
                continue
            try:
                if path.stat().st_size > _MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            candidates.append(path)

        candidates.sort(key=lambda p: _priority(p, repo_path))

        if len(candidates) > _MAX_FILES_SCANNED:
            logger.warning(
                "TreeSitterParser: %s eligible files under %s, scanning the "
                "highest-priority %s (real source before tests/docs/examples)",
                len(candidates), repo_path, _MAX_FILES_SCANNED,
            )
        yield from candidates[:_MAX_FILES_SCANNED]

    def parse(self, repo_path: Path) -> list[CodeChunk]:
        parsed_files: list[ParsedFile] = []

        for path in self._iter_source_files(repo_path):
            language = _detect_language(path)
            try:
                source = path.read_bytes()
            except OSError:
                continue

            tree = None
            if language != "text":
                parser = self._get_parser(language)
                if parser is not None:
                    try:
                        tree = parser.parse(source)
                    except Exception:
                        tree = None

            parsed_files.append(ParsedFile(path=path, language=language, source=source, tree=tree))

        return self.chunk_builder.build_chunks(repo_path, parsed_files)
