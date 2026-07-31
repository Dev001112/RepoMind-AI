"""Detects GPU/CUDA requirements."""

import os
import re
from pathlib import Path

from app.services.repository.detectors.base import BaseDetector

_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist",
    "build", ".next", "target", "vendor", ".idea", ".vscode",
    ".pytest_cache", ".mypy_cache", ".tox",
}

_MANIFEST_NAMES = {"requirements.txt", "pyproject.toml", "package.json"}
_SOURCE_EXTS = {".py", ".js", ".ts"}
_MAX_FILE_SIZE = 1 * 1024 * 1024  # 1MB
_MAX_SOURCE_FILES = 300

_CUDA_TAG_RE = re.compile(r"cu\d{2,3}|\+cu", re.IGNORECASE)
# Word-boundary matches, not bare substrings -- a plain "jax" in bare `in` would
# also match inside "ajax", which shows up in any web project's docs/examples.
# `torch\w*` (no trailing boundary) intentionally also catches torchvision/torchaudio.
_WEAK_GPU_PATTERNS = (
    re.compile(r"\btorch\w*\b"),
    re.compile(r"\btensorflow\b"),
    re.compile(r"\bjax\b"),
)
_SOURCE_CUDA_MARKERS = ("torch.cuda", "cupy", "CUDA_VISIBLE_DEVICES")


def _skip_dir(name: str) -> bool:
    return name in _SKIP_DIRS or name.endswith(".egg-info")


def _read_small(path: Path) -> str | None:
    """Read a file's text if it's small enough, else None. Never raises."""
    try:
        if path.stat().st_size > _MAX_FILE_SIZE:
            return None
        return path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, ValueError):
        return None


class CudaDetector(BaseDetector):
    def __init__(self) -> None:
        pass

    def detect(self, repo_path: Path) -> dict:
        """Check manifests for CUDA build tags/nvidia- packages, Dockerfiles
        for CUDA base images, and source files for torch.cuda/cupy/
        CUDA_VISIBLE_DEVICES usage."""
        repo_path = Path(repo_path)
        cuda_required = False
        gpu_signal = False
        scanned_sources = 0

        if not repo_path.is_dir():
            return {"gpu_required": False, "cuda_required": False}

        try:
            for dirpath, dirnames, filenames in os.walk(repo_path):
                if cuda_required and gpu_signal:
                    break  # nothing left that could change the outcome

                dirnames[:] = [d for d in dirnames if not _skip_dir(d)]
                depth = len(Path(dirpath).relative_to(repo_path).parts)

                for name in filenames:
                    file_path = Path(dirpath) / name

                    if name in _MANIFEST_NAMES:
                        content = _read_small(file_path)
                        if content:
                            lower = content.lower()
                            if _CUDA_TAG_RE.search(content) or "nvidia-" in lower:
                                cuda_required = True
                            if any(pattern.search(lower) for pattern in _WEAK_GPU_PATTERNS):
                                gpu_signal = True

                    elif name.lower().startswith("dockerfile") and depth <= 1:
                        content = _read_small(file_path)
                        if content:
                            for line in content.splitlines():
                                stripped = line.strip()
                                if stripped.upper().startswith("FROM") and "cuda" in stripped.lower():
                                    cuda_required = True
                                    break

                    elif (
                        not cuda_required
                        and scanned_sources < _MAX_SOURCE_FILES
                        and Path(name).suffix in _SOURCE_EXTS
                    ):
                        scanned_sources += 1
                        content = _read_small(file_path)
                        if content and any(marker in content for marker in _SOURCE_CUDA_MARKERS):
                            cuda_required = True
        except OSError:
            pass  # walking the tree failed partway through; use what we found

        gpu_required = cuda_required or gpu_signal
        return {"gpu_required": gpu_required, "cuda_required": cuda_required}
