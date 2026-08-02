"""Metadata Extractor: pulls concrete repository facts out of the query text
-- a framework, a language, a path, a file, a symbol, an API route -- and
turns them into the pre-filters the retriever applies.

Fully deterministic. The repo profile (languages/frameworks present in the
index) is used to disambiguate: "is this a framework word or a coincidence?"
Path-like tokens and `word()`/`Class` shapes are handled textually.

Output: ExtractedMetadata -> planner builds the final ChunkFilters.
"""

import re
import uuid
from dataclasses import dataclass, field

from app.models.schemas.retrieval import ExtractedMetadata

_FILE_RE = re.compile(r"(?:[\w.-]+\.)+[a-z0-9]{1,8}\b", re.IGNORECASE)
_PATH_RE = re.compile(r"\b[\w.-]+(?:/[\w.-]+){1,5}\b")
_API_ROUTE_RE = re.compile(r"/[\w{}:.?=&%-]{1,80}")
_FUNCTION_RE = re.compile(r"\b[a-z_]\w*\(\)")
_SYMBOL_RE = re.compile(r"\b[A-Z][A-Za-z0-9_]{1,40}\b|\b[a-z_][a-z0-9_]{2,40}(?:\.\w+){0,2}\b")

_KNOWN_LANGUAGES = {
    "python", "py", "javascript", "js", "typescript", "ts", "tsx", "jsx",
    "java", "kotlin", "go", "golang", "rust", "c", "cpp", "c++", "csharp",
    "c#", "php", "ruby", "swift", "dart", "scala", "elixir", "erlang",
    "haskell", "lua", "shell", "bash", "sql", "html", "css", "yaml", "yml",
    "json", "toml", "makefile", "dockerfile", "vue", "svelte",
}
_KNOWN_FRAMEWORKS = {
    "flask", "django", "fastapi", "express", "next", "react", "vue", "angular",
    "svelte", "spring", "rails", "laravel", "gin", "echo", "fiber", "actix",
    "rocket", "tornado", "aiohttp", "starlette", "bootstrap", "tailwind",
    "redux", "tensorflow", "pytorch", "pytest", "junit", "pandas", "numpy",
    "sqlalchemy", "celery", "redis", "kafka", "grpc", "graphql",
}
_KNOWN_TYPES = {
    "endpoint", "api", "api_endpoint", "function", "class", "file", "folder",
    "database", "table", "dependency", "security", "performance", "architecture",
    "documentation", "deployment", "testing", "cicd", "docker", "cuda",
}

_FILE_EXT_TO_LANG = {
    "py": "python", "js": "javascript", "ts": "typescript", "tsx": "typescript",
    "jsx": "javascript", "java": "java", "kt": "kotlin", "go": "go", "rs": "rust",
    "c": "c", "cpp": "cpp", "cc": "cpp", "cs": "csharp", "php": "php",
    "rb": "ruby", "swift": "swift", "dart": "dart", "scala": "scala",
    "lua": "lua", "sh": "shell", "bash": "shell", "sql": "sql", "html": "html",
    "css": "css", "yaml": "yaml", "yml": "yaml", "json": "json", "toml": "toml",
    "md": "documentation", "rst": "documentation", "txt": "documentation",
    "lock": "dependency", "mod": "go", "sum": "go",
}


@dataclass
class RepoProfile:
    """Cheap facts about the indexed repository, used to disambiguate the
    query: only values that actually exist in the index are worth filtering on.
    The engine builds this from stats + a payload scan (languages, frameworks)
    and optionally the file list."""

    repository_id: str = ""
    languages: set[str] = field(default_factory=set)
    frameworks: set[str] = field(default_factory=set)
    files: set[str] = field(default_factory=set)
    directories: set[str] = field(default_factory=set)
    api_routes: set[str] = field(default_factory=set)
    symbols: set[str] = field(default_factory=set)

    @property
    def empty(self) -> bool:
        return not (self.languages or self.frameworks or self.files)


class MetadataExtractor:
    """Rule-based extraction; never raises, always returns ExtractedMetadata."""

    def __init__(self, profile: RepoProfile | None = None) -> None:
        self.profile = profile or RepoProfile()

    def extract(self, query: str) -> ExtractedMetadata:
        meta = ExtractedMetadata()
        lowered = query.lower()
        tokens = set(_TOKEN_RE_PLAIN(lowered))

        # 1. Explicit type words ("the api endpoint ...", "show me the class").
        for token in tokens:
            if token in _KNOWN_TYPES:
                meta.type = token
                break
            if token in {"endpoints", "apis"}:
                meta.type = "api_endpoint"

        # 2. Language / framework -- only if it exists in the repo profile
        #    (or is unambiguously a language name even when unknown).
        for token in tokens:
            if token in _KNOWN_LANGUAGES and (not self.profile.empty or token in _KNOWN_LANGUAGES):
                if token in self.profile.languages or not self.profile.empty:
                    meta.language = _normalize_language(token)
                    break
        for token in tokens:
            if token in _KNOWN_FRAMEWORKS and token in self.profile.frameworks:
                meta.framework = token
                break

        # 3. Path/file tokens -- a full path ("api/auth.py") beats the bare
        #    filename ("auth.py") the file regex would find first.
        path_match = _PATH_RE.search(query)
        if path_match:
            path = path_match.group(0)
            ext = path.rsplit(".", 1)[-1].lower()
            if "/" in path or ext in _FILE_EXT_TO_LANG or "." in path.rsplit("/", 1)[-1]:
                file_name = path.lstrip("/")
                meta.file = file_name
                if "/" in file_name:
                    meta.directory = file_name.rsplit("/", 1)[0]
                if meta.language is None and ext in _FILE_EXT_TO_LANG:
                    lang = _FILE_EXT_TO_LANG[ext]
                    if lang not in {"documentation", "dependency"}:
                        meta.language = lang
        if meta.file is None:
            file_match = _FILE_RE.search(query)
            if file_match:
                file_name = file_match.group(0).lstrip("/")
                meta.file = file_name
                if meta.directory is None and "/" in file_name:
                    meta.directory = file_name.rsplit("/", 1)[0]
                ext = file_name.rsplit(".", 1)[-1].lower()
                if meta.language is None and ext in _FILE_EXT_TO_LANG:
                    lang = _FILE_EXT_TO_LANG[ext]
                    if lang not in {"documentation", "dependency"}:
                        meta.language = lang

        # 4. API route ("/login", "GET /api/users").
        route_match = _API_ROUTE_RE.search(query)
        if route_match:
            route = route_match.group(0).lower()
            if len(route) >= 3:
                meta.api_route = route
                if meta.type is None:
                    meta.type = "api_endpoint"

        # 5. Function / class / symbol names.
        func_match = _FUNCTION_RE.search(query)
        if func_match and not query.endswith(func_match.group(0) + ")"):
            name = func_match.group(0)[:-2]
            meta.symbol = name
            if meta.type is None:
                meta.type = "function"
        symbol_match = _SYMBOL_RE.search(query)
        if symbol_match and meta.symbol is None:
            candidate = symbol_match.group(0)
            if candidate.lower() not in tokens or len(candidate) >= 5:
                meta.symbol = candidate
                if meta.type is None and candidate[0].isupper():
                    meta.type = "class"

        return meta


_TOKEN_RE_PLAIN = re.compile(r"[a-z0-9_]+").findall


def _normalize_language(token: str) -> str:
    aliases = {
        "py": "python", "js": "javascript", "ts": "typescript",
        "tsx": "typescript", "jsx": "javascript", "kt": "kotlin",
        "golang": "go", "cpp": "cpp", "c++": "cpp", "cs": "csharp",
        "c#": "csharp", "rb": "ruby", "sh": "shell",
    }
    return aliases.get(token, token)


def get_metadata_extractor(profile: RepoProfile | None = None) -> MetadataExtractor:
    return MetadataExtractor(profile)
