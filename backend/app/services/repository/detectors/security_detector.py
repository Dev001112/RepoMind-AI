"""Deterministic first-pass security scan: hardcoded secrets, a committed
.env file, and a short list of known-risky code patterns.

Not a full SAST tool -- genuinely unreliable things (outdated-dependency
CVEs, business-logic flaws) need real vulnerability databases and dynamic
analysis, which is out of scope for a cheap static pass. What's here is
cheap, deterministic, and real.
"""

import os
import re
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from app.services.repository.detectors.base import Detector
from app.utils.file_utils import SKIP_DIRS

_MAX_FILE_BYTES = 1_000_000
_MAX_FILES_SCANNED = 500
_MAX_FINDINGS = 50

_SOURCE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".rb", ".php", ".go", ".java"}

# Obvious test-fixture/placeholder values -- "password='test'" in a test helper's
# default argument is an extremely common pattern, not a real hardcoded credential.
# Real accidental secrets don't look like these.
_PLACEHOLDER_VALUES = {
    "test", "password", "changeme", "change_me", "xxx", "xxxx", "example",
    "placeholder", "secret", "your_password_here", "123456", "admin", "demo",
    "sample", "fake", "dummy", "todo", "foo", "bar", "foobar",
}

# (pattern, label, capture-group index holding the secret VALUE to check against
# _PLACEHOLDER_VALUES -- None if the pattern itself is inherently high-confidence
# with no meaningful "placeholder" concept, e.g. an AWS key format or PEM header).
_SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "hardcoded AWS access key", None),
    (re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"), "hardcoded private key", None),
    (
        re.compile(r"""(?i)(?:api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*["']([A-Za-z0-9_\-]{16,})["']"""),
        "hardcoded API key/token",
        1,
    ),
    (re.compile(r"""(?i)password\s*[:=]\s*["']([^"'\s]{4,})["']"""), "hardcoded password", 1),
]

_RISKY_CODE_PATTERNS = [
    (re.compile(r"\beval\("), "use of eval()", None),
    (re.compile(r"\bexec\("), "use of exec()", None),
    (re.compile(r"subprocess\.\w+\([^)]*shell\s*=\s*True"), "subprocess call with shell=True", None),
    (re.compile(r"\bpickle\.loads?\("), "use of pickle.load/loads (unsafe deserialization)", None),
    (re.compile(r"dangerouslySetInnerHTML"), "React dangerouslySetInnerHTML usage", None),
]


def _skip_dir(name: str) -> bool:
    return name in SKIP_DIRS or name.endswith(".egg-info")


def _env_committed_without_gitignore(repo_path: Path) -> list[str]:
    env_path = repo_path / ".env"
    if not env_path.is_file():
        return []
    gitignore_path = repo_path / ".gitignore"
    if gitignore_path.is_file():
        try:
            text = gitignore_path.read_text(encoding="utf-8", errors="ignore")
            if any(line.strip() in (".env", "*.env", "/.env") for line in text.splitlines()):
                return []
        except OSError:
            pass
    return [".env file is committed to the repository and not covered by .gitignore"]


class SecurityDetectionResult(BaseModel):
    security_findings: list[str] = []


class SecurityDetector(Detector[SecurityDetectionResult]):
    result_model: ClassVar[type[SecurityDetectionResult]] = SecurityDetectionResult

    def confidence(self, data: SecurityDetectionResult) -> float:
        # Regex pattern matches are real, but "is this actually exploitable" is
        # a judgment call this cheap static pass can't make -- flag as heuristic.
        return 0.8 if data.security_findings else 1.0

    def detect(self, repo_path: Path) -> SecurityDetectionResult:
        repo_path = Path(repo_path)
        if not repo_path.is_dir():
            return SecurityDetectionResult()

        findings: list[str] = list(_env_committed_without_gitignore(repo_path))
        seen: set[str] = set()
        scanned = 0

        try:
            for dirpath, dirnames, filenames in os.walk(repo_path):
                if len(findings) >= _MAX_FINDINGS or scanned >= _MAX_FILES_SCANNED:
                    break
                dirnames[:] = [d for d in dirnames if not _skip_dir(d)]

                for filename in filenames:
                    if len(findings) >= _MAX_FINDINGS or scanned >= _MAX_FILES_SCANNED:
                        break
                    path = Path(dirpath) / filename
                    if path.suffix.lower() not in _SOURCE_EXTS:
                        continue
                    try:
                        if path.stat().st_size > _MAX_FILE_BYTES:
                            continue
                        content = path.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        continue
                    scanned += 1

                    rel = path.relative_to(repo_path).as_posix()
                    for pattern, label, value_group in (*_SECRET_PATTERNS, *_RISKY_CODE_PATTERNS):
                        if len(findings) >= _MAX_FINDINGS:
                            break
                        key = f"{label}::{rel}"
                        if key in seen:
                            continue
                        match = pattern.search(content)
                        if not match:
                            continue
                        if value_group is not None and match.group(value_group).lower() in _PLACEHOLDER_VALUES:
                            continue
                        seen.add(key)
                        findings.append(f"{label} in {rel}")
        except OSError:
            pass

        return SecurityDetectionResult(security_findings=findings)
