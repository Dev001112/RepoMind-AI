"""Best-effort REST endpoint discovery via regex over source files.

Not a real API-spec extractor (no OpenAPI/AST-level resolution) -- just
common decorator/call patterns for the frameworks this project already
recognizes (Flask/FastAPI/Express/NestJS). Low confidence by design.
"""

import re
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from app.models.schemas.knowledge import ApiEndpoint
from app.services.repository.detectors.base import Detector
from app.utils.file_utils import SKIP_DIRS

_MAX_FILE_SIZE = 512 * 1024
_MAX_FILES_SCANNED = 400
_MAX_ENDPOINTS = 200
_SOURCE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx"}

# Gate the (more expensive) file walk behind a cheap manifest-text check --
# skip entirely for repos with no recognized web framework at all.
_GATE_MANIFESTS = ("requirements.txt", "pyproject.toml", "package.json", "Pipfile")
_GATE_SIGNATURES = ("flask", "fastapi", "express", "@nestjs/core", "django")

# `@app.get("/x")`, `router.post('/x')`, `@router.get("/x")`, etc.
_METHOD_CALL_RE = re.compile(
    r"""@?\b(?:app|router)\.(get|post|put|delete|patch)\(\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
# Flask's `@app.route("/x")` (method defaults to GET unless methods= is given).
_FLASK_ROUTE_RE = re.compile(r"""@app\.route\(\s*["']([^"']+)["']""")
# NestJS-style `@Get('/x')`.
_NEST_RE = re.compile(r"""@(Get|Post|Put|Delete|Patch)\(\s*["']?([^"')]*)["']?\s*\)""")


class ApiSurfaceDetectionResult(BaseModel):
    endpoints: list[ApiEndpoint] = []


def _repo_has_web_framework(repo_path: Path) -> bool:
    for name in _GATE_MANIFESTS:
        path = repo_path / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        if any(sig in text for sig in _GATE_SIGNATURES):
            return True
    return False


class ApiSurfaceDetector(Detector[ApiSurfaceDetectionResult]):
    result_model: ClassVar[type[ApiSurfaceDetectionResult]] = ApiSurfaceDetectionResult

    def confidence(self, data: ApiSurfaceDetectionResult) -> float:
        return 0.6 if data.endpoints else 1.0

    def detect(self, repo_path: Path) -> ApiSurfaceDetectionResult:
        if not _repo_has_web_framework(repo_path):
            return ApiSurfaceDetectionResult()

        endpoints: list[ApiEndpoint] = []
        scanned = 0
        try:
            for dirpath, dirnames, filenames in Path(repo_path).walk():
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                if scanned >= _MAX_FILES_SCANNED or len(endpoints) >= _MAX_ENDPOINTS:
                    break
                for filename in filenames:
                    if scanned >= _MAX_FILES_SCANNED or len(endpoints) >= _MAX_ENDPOINTS:
                        break
                    file_path = dirpath / filename
                    if file_path.suffix.lower() not in _SOURCE_EXTS:
                        continue
                    try:
                        if file_path.stat().st_size > _MAX_FILE_SIZE:
                            continue
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        continue
                    scanned += 1
                    rel = file_path.relative_to(repo_path).as_posix()

                    for match in _METHOD_CALL_RE.finditer(content):
                        endpoints.append(
                            ApiEndpoint(method=match.group(1).upper(), path=match.group(2), file=rel)
                        )
                    for match in _FLASK_ROUTE_RE.finditer(content):
                        endpoints.append(ApiEndpoint(method="GET", path=match.group(1), file=rel))
                    for match in _NEST_RE.finditer(content):
                        endpoints.append(
                            ApiEndpoint(method=match.group(1).upper(), path=match.group(2) or "/", file=rel)
                        )
        except OSError:
            pass

        return ApiSurfaceDetectionResult(endpoints=endpoints[:_MAX_ENDPOINTS])
