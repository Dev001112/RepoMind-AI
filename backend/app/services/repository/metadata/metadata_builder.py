"""Aggregates raw detector/parser outputs into a single plain dict.

No deterministic-vs-LLM decisions happen here, just merging the detectors'
own dicts plus two cheap structural facts (folder tree, main entry point)
that don't warrant their own detector class.
"""

from pathlib import Path

from app.utils.file_utils import build_folder_tree

# Checked in order; the first that exists at repo_path's root (or the listed
# subpath) wins. Deliberately simple -- a real "which file actually runs"
# answer would need to read setup.py entry_points / package.json "main" /
# Dockerfile CMD, which is more than this Phase 2 pass covers.
_ENTRY_POINT_CANDIDATES = [
    "main.py", "app.py", "manage.py", "wsgi.py", "asgi.py", "run.py",
    "index.js", "index.ts", "server.js", "app.js", "src/index.js", "src/index.ts",
    "src/main.rs", "main.go", "cmd/main.go",
]


def _find_main_entry_point(repo_path: Path) -> str | None:
    for candidate in _ENTRY_POINT_CANDIDATES:
        if (repo_path / candidate).is_file():
            return candidate
    return None


class MetadataBuilder:
    def __init__(self) -> None:
        pass

    def build(self, repo_path: Path, **detector_outputs: dict) -> dict:
        """Merge every detector output dict into one flat dict, and add the
        two structural facts computed here directly."""
        metadata: dict = {}
        for output in detector_outputs.values():
            metadata.update(output)

        metadata["folder_structure"] = build_folder_tree(repo_path)
        metadata["main_entry_point"] = _find_main_entry_point(repo_path)
        return metadata
