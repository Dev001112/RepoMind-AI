"""Extracts structured info out of a repo's README."""

import re
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from app.services.repository.detectors.base import Detector

# Any markdown heading, level 1-6, used to find section boundaries.
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*$")
# Exactly one '#' followed by a space -- the top-level H1.
_H1_RE = re.compile(r"^#(?!#)\s+(.*?)\s*$")
_FENCE_RE = re.compile(r"^```(\S*)?\s*$")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s+(.*)$")

_LICENSE_PHRASES = [
    (lambda low: "mit license" in low, "MIT"),
    (lambda low: "apache license" in low, "Apache-2.0"),
    (lambda low: "gnu general public license" in low and "version 3" in low, "GPL-3.0"),
    (lambda low: "gnu general public license" in low and "version 2" in low, "GPL-2.0"),
    (lambda low: "bsd" in low, "BSD"),
    # BSD-3-Clause's actual boilerplate text often never says "BSD" anywhere (e.g.
    # Flask's real LICENSE.txt) -- its distinctive opening line is a stronger signal
    # than the name itself.
    (lambda low: "redistribution and use in source and binary forms" in low, "BSD"),
]


def _find_file(repo_path: Path, candidates_lower: list[str]) -> Path | None:
    """Case-insensitive lookup of the first matching filename (by preference
    order of `candidates_lower`) directly under repo_path."""
    try:
        entries: dict[str, Path] = {}
        for entry in repo_path.iterdir():
            if entry.is_file():
                entries.setdefault(entry.name.lower(), entry)
    except OSError:
        return None
    for candidate in candidates_lower:
        if candidate in entries:
            return entries[candidate]
    return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _clean_inline(text: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*([^*]*)\*\*", r"\1", text)
    text = re.sub(r"__([^_]*)__", r"\1", text)
    text = re.sub(r"\*([^*]*)\*", r"\1", text)
    text = re.sub(r"_([^_]*)_", r"\1", text)
    return text.strip()


def _clean_name(text: str) -> str | None:
    text = _clean_inline(text)
    text = re.sub(r"^[^\w]+", "", text)  # drop leading emoji/symbols
    text = text.strip()
    return text or None


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last_space = cut.rfind(" ")
    if last_space > 0:
        cut = cut[:last_space]
    return cut.rstrip() + "..."


def _is_badge_line(line: str) -> bool:
    """A line that, once every markdown image / link-wrapped image is
    stripped out of it, has nothing left."""
    stripped = line.strip()
    if not stripped:
        return False
    cleaned = re.sub(r"\[!\[.*?\]\(.*?\)\]\(.*?\)", "", stripped)
    cleaned = re.sub(r"!\[.*?\]\(.*?\)", "", cleaned)
    return cleaned.strip() == ""


def _match_license_phrase(text: str) -> str | None:
    low = text.lower()
    for matches, license_id in _LICENSE_PHRASES:
        if matches(low):
            return license_id
    return None


def _find_section(lines: list[str], predicate) -> tuple[int, int] | None:
    """First heading whose text satisfies `predicate` -> (start, end) line
    range of its body, ending at the next heading (any level) or EOF."""
    n = len(lines)
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m and predicate(m.group(1)):
            j = i + 1
            while j < n and not _HEADING_RE.match(lines[j]):
                j += 1
            return i + 1, j
    return None


def _extract_description(lines: list[str], start_idx: int) -> str | None:
    n = len(lines)
    i = start_idx
    while i < n:
        while i < n and not lines[i].strip():
            i += 1
        if i >= n or _HEADING_RE.match(lines[i]):
            break
        para = []
        while i < n and lines[i].strip() and not _HEADING_RE.match(lines[i]):
            para.append(lines[i])
            i += 1
        content = [l.strip() for l in para if not _is_badge_line(l)]
        content = [l for l in content if l]
        if content:
            return _truncate(_clean_inline(" ".join(content)), 400)
    return None


def _extract_installation_steps(lines: list[str]) -> list[str]:
    section = _find_section(lines, lambda t: "install" in t.lower())
    if section is None:
        section = _find_section(lines, lambda t: "getting started" in t.lower())
    if section is None:
        return []

    section_lines = lines[section[0]:section[1]]
    n = len(section_lines)
    steps: list[str] = []
    found_code_block = False
    i = 0
    while i < n:
        if _FENCE_RE.match(section_lines[i].strip()):
            found_code_block = True
            i += 1
            block: list[str] = []
            while i < n and not _FENCE_RE.match(section_lines[i].strip()):
                block.append(section_lines[i])
                i += 1
            i += 1  # step past the closing fence
            for raw in block:
                item = raw.strip()
                if not item:
                    continue
                if item.startswith("$ "):
                    item = item[2:].strip()
                if item:
                    steps.append(item)
        else:
            i += 1

    if found_code_block:
        return steps

    for line in section_lines:
        m = _LIST_ITEM_RE.match(line)
        if m:
            item = _clean_inline(m.group(1).strip())
            if item:
                steps.append(item)
    return steps


def _extract_license_from_readme(lines: list[str]) -> str | None:
    section = _find_section(lines, lambda t: "license" in t.lower())
    if section is None:
        return None
    text = "\n".join(lines[section[0]:section[1]])[:500]
    return _match_license_phrase(text)


def _detect_license(repo_path: Path, md_lines: list[str] | None) -> str | None:
    license_path = _find_file(repo_path, ["license", "license.md", "license.txt"])
    if license_path is not None:
        content = _read_text(license_path)[:500]
        return _match_license_phrase(content) or "Unknown"
    if md_lines is not None:
        return _extract_license_from_readme(md_lines)
    return None


def _parse_markdown(text: str):
    lines = text.splitlines()
    name = None
    description = None
    for i, line in enumerate(lines):
        m = _H1_RE.match(line)
        if m:
            name = _clean_name(m.group(1))
            description = _extract_description(lines, i + 1)
            break
    installation_steps = _extract_installation_steps(lines)
    return name, description, installation_steps, lines


def _parse_generic(text: str):
    """Crude best-effort parse for README.rst / README.txt / extension-less
    README files -- no markdown heading syntax to lean on."""
    lines = text.splitlines()
    n = len(lines)
    idx = 0
    while idx < n and not lines[idx].strip():
        idx += 1

    name = None
    if idx < n:
        name = lines[idx].strip().strip("=-#*~^\" \t") or None
        idx += 1
        if idx < n and lines[idx].strip() and set(lines[idx].strip()) <= set("=-~^"):
            idx += 1  # rst-style underline under the title

    while idx < n and not lines[idx].strip():
        idx += 1
    para = []
    while idx < n and lines[idx].strip():
        para.append(lines[idx].strip())
        idx += 1
    description = _truncate(" ".join(para), 400) if para else None

    steps: list[str] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or "install" not in stripped.lower() or len(stripped) >= 60:
            continue
        underline_next = (
            i + 1 < n and lines[i + 1].strip() and set(lines[i + 1].strip()) <= set("=-~^")
        )
        if not (underline_next or stripped.endswith(":") or stripped.isupper()):
            continue
        start = i + 2 if underline_next else i + 1
        j = start
        while j < n and not lines[j].strip():
            j += 1  # skip the blank line that usually follows a heading
        while j < n and lines[j].strip():
            raw = lines[j].strip()
            m = _LIST_ITEM_RE.match(raw)
            if m:
                item = m.group(1).strip()
            else:
                item = raw[2:].strip() if raw.startswith("$ ") else raw
            if item:
                steps.append(item)
            j += 1
        break

    return name, description, steps


class ReadmeParseResult(BaseModel):
    name: str | None = None
    description: str | None = None
    license: str | None = None
    installation_steps: list[str] = []
    has_readme: bool = False
    has_contributing: bool = False
    has_license_file: bool = False


class ReadmeParser(Detector[ReadmeParseResult]):
    result_model: ClassVar[type[ReadmeParseResult]] = ReadmeParseResult

    def detect(self, repo_path: Path) -> ReadmeParseResult:
        """Locate the repo's README and pull out its name, description,
        installation steps, and license (falling back to the LICENSE file
        or a README "## License" section)."""
        has_contributing = _find_file(repo_path, ["contributing.md", "contributing"]) is not None
        has_license_file = _find_file(repo_path, ["license", "license.md", "license.txt"]) is not None

        readme_path = _find_file(
            repo_path, ["readme.md", "readme.rst", "readme.txt", "readme"]
        )
        if readme_path is None:
            # No README doesn't mean no LICENSE -- still check for a standalone one.
            return ReadmeParseResult(
                license=_detect_license(repo_path, None),
                has_contributing=has_contributing,
                has_license_file=has_license_file,
            )

        text = _read_text(readme_path)
        if readme_path.suffix.lower() == ".md":
            name, description, installation_steps, md_lines = _parse_markdown(text)
            license_value = _detect_license(repo_path, md_lines)
        else:
            name, description, installation_steps = _parse_generic(text)
            license_value = _detect_license(repo_path, None)

        return ReadmeParseResult(
            name=name,
            description=description,
            license=license_value,
            installation_steps=installation_steps,
            has_readme=True,
            has_contributing=has_contributing,
            has_license_file=has_license_file,
        )
