"""Small, generic filesystem helpers used across the app."""

from pathlib import Path

# Common vendored/build/vcs noise to skip when walking a cloned repository.
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist",
    "build", ".next", "target", "vendor", ".idea", ".vscode", ".pytest_cache",
    ".mypy_cache", ".tox",
}


def _skip_entry(name: str) -> bool:
    return name in SKIP_DIRS or name.endswith(".egg-info")


def build_folder_tree(repo_path: str | Path, max_depth: int = 2) -> dict:
    """A shallow nested dict of repo_path's structure: dirs map to nested
    dicts, files map to None. Depth-limited and skip-dir-filtered so it stays
    small even for large repos."""
    repo_path = Path(repo_path)

    def _walk(directory: Path, depth: int) -> dict:
        tree: dict = {}
        try:
            entries = sorted(directory.iterdir(), key=lambda p: p.name)
        except OSError:
            return tree
        for entry in entries:
            if _skip_entry(entry.name):
                continue
            if entry.is_dir():
                tree[entry.name] = _walk(entry, depth + 1) if depth < max_depth else {}
            else:
                tree[entry.name] = None
        return tree

    return _walk(repo_path, 1)


def ensure_dir(path: str | Path) -> Path:
    """Create `path` (and parents) if it doesn't exist, and return it as a Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_join(base: str | Path, *parts: str) -> Path:
    """Join `parts` onto `base`, raising if the result escapes `base`.

    Prevents path-traversal (e.g. via '..' in an uploaded filename).
    """
    base_path = Path(base).resolve()
    joined = base_path.joinpath(*parts).resolve()
    if base_path not in joined.parents and joined != base_path:
        raise ValueError(f"'{joined}' escapes base directory '{base_path}'")
    return joined


def get_file_size_mb(path: str | Path) -> float:
    """Return the file size at `path` in megabytes."""
    return Path(path).stat().st_size / (1024 * 1024)
