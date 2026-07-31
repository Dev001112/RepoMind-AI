"""Lightweight per-file import graph -- feeds a future dependency-graph
visualization. Regex-based (imports have a very regular, line-anchored
syntax), not a full resolver: import targets are the raw module path/string
as written (e.g. "app.core.config", "./utils"), not resolved to an exact
file within the repo.
"""

import re
from pathlib import Path

from app.utils.file_utils import SKIP_DIRS

_MAX_FILES = 500
_MAX_FILE_BYTES = 200_000
_MAX_IMPORTS_PER_FILE = 20

_PY_IMPORT_RE = re.compile(r"^\s*(?:from\s+(\S+)\s+import|import\s+(\S+))", re.MULTILINE)
_JS_IMPORT_RE = re.compile(r"""(?:import\s.*?from\s+|require\()\s*['"]([^'"]+)['"]""")


def _extract_python_imports(text: str) -> list[str]:
    modules = []
    for match in _PY_IMPORT_RE.finditer(text):
        module = match.group(1) or match.group(2)
        if module:
            modules.append(module.split(",")[0].strip())
    return modules


def _extract_js_imports(text: str) -> list[str]:
    return [m.group(1) for m in _JS_IMPORT_RE.finditer(text)]


class ImportGraphBuilder:
    def __init__(self) -> None:
        pass

    def build(self, repo_path: Path) -> dict[str, list[str]]:
        """{repo-relative file path: [raw import targets]} for Python/JS/TS files."""
        repo_path = Path(repo_path)
        graph: dict[str, list[str]] = {}
        if not repo_path.is_dir():
            return graph

        scanned = 0
        for path in repo_path.rglob("*"):
            if scanned >= _MAX_FILES:
                break
            if path.is_symlink() or not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.relative_to(repo_path).parts):
                continue
            suffix = path.suffix.lower()
            if suffix not in (".py", ".js", ".jsx", ".ts", ".tsx"):
                continue
            try:
                if path.stat().st_size > _MAX_FILE_BYTES:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            scanned += 1

            imports = _extract_python_imports(text) if suffix == ".py" else _extract_js_imports(text)
            if imports:
                # .as_posix(), not str() -- same fix as chunk_builder.py's CodeChunk.file_path:
                # str(Path) uses backslashes on Windows, which wouldn't match the forward-slash
                # paths used everywhere else (URLs, embedded chunk metadata).
                rel_path = path.relative_to(repo_path).as_posix()
                graph[rel_path] = sorted(set(imports))[:_MAX_IMPORTS_PER_FILE]

        return graph
