"""Plain structural facts about a repo that don't warrant their own detector:
folder tree, main entry point guess, total file count. All three are simple
deterministic lookups with no meaningful failure mode to track, so they stay
as helper functions the Knowledge Builder calls directly rather than going
through the full Detector/DetectorResult envelope.
"""

from pathlib import Path

from app.utils.file_utils import SKIP_DIRS, build_folder_tree

# Checked in order; the first that exists at repo_path's root (or the listed
# subpath) wins. Deliberately simple -- a real "which file actually runs"
# answer would need to read setup.py entry_points / package.json "main" /
# Dockerfile CMD, which is more than this pass covers.
_ENTRY_POINT_CANDIDATES = [
    "main.py", "app.py", "manage.py", "wsgi.py", "asgi.py", "run.py",
    "index.js", "index.ts", "server.js", "app.js", "src/index.js", "src/index.ts",
    "src/main.rs", "main.go", "cmd/main.go",
]


def find_main_entry_point(repo_path: Path) -> str | None:
    for candidate in _ENTRY_POINT_CANDIDATES:
        if (repo_path / candidate).is_file():
            return candidate
    return None


def folder_structure(repo_path: Path) -> dict:
    return build_folder_tree(repo_path)


def count_total_files(repo_path: Path) -> int:
    total = 0
    try:
        for _dirpath, dirnames, filenames in Path(repo_path).walk():
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")]
            total += len(filenames)
    except OSError:
        pass
    return total
