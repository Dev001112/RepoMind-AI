"""Extracts an uploaded zip archive to local disk."""

import zipfile
from pathlib import Path

from app.services.repository.clone.base import BaseCloner


class ZipExtractor(BaseCloner):
    def __init__(self) -> None:
        pass

    def clone(self, source: str, dest: Path) -> Path:
        """Extract the zip at `source` into `dest`, guarding against zip-slip
        path traversal, and unwrapping a single top-level wrapper directory
        (e.g. GitHub's `<repo>-<branch>/` zip layout) if present."""
        dest_resolved = dest.resolve()

        with zipfile.ZipFile(source) as zf:
            for info in zf.infolist():
                member_path = (dest / info.filename).resolve()
                if not member_path.is_relative_to(dest_resolved):
                    raise ValueError("unsafe zip: path traversal detected")

            zf.extractall(dest)

        # extractall() never creates `dest` itself for a zip with zero entries
        entries = list(dest.iterdir()) if dest.exists() else []
        if len(entries) == 1 and entries[0].is_dir():
            return entries[0]
        return dest
