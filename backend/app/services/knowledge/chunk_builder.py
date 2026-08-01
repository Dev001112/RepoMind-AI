"""Turns a RepositoryKnowledge report into semantic KnowledgeChunks.

The milestone rule is "never embed files, embed knowledge": this builder is
the only place knowledge becomes chunks. Every section of the report that
describes *meaning* (this endpoint needs auth, this folder is the service
layer, this database backs the API) becomes a small, self-contained,
embeddable chunk with a stable id, a content checksum, and typed edges to the
other chunks it relates to.

Ids and checksums are deterministic functions of content, so the embedding
service can skip unchanged chunks on re-analysis and version the rest.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone

from app.models.schemas.knowledge import ApiEndpoint, RepositoryKnowledge
from app.models.schemas.knowledge_chunks import ChunkMetadata, ChunkRelationship, KnowledgeChunk

# Closed vocabulary of chunk types (the milestone's semantic types plus the
# smaller facets that still deserve their own chunk). Kept as plain strings --
# they land in Qdrant payloads and are what the frontend renders as badges.
SUMMARY = "summary"
ARCHITECTURE = "architecture"
FOLDER = "folder"
FILE = "file"
API_ENDPOINT = "api_endpoint"
DATABASE = "database"
FRAMEWORK = "framework"
DEPENDENCY = "dependency"
DOCKER = "docker"
CUDA = "cuda"
CICD = "cicd"
DEPLOYMENT = "deployment"
TESTING = "testing"
DOCUMENTATION = "documentation"
PERFORMANCE = "performance"
SECURITY = "security"
QUALITY = "quality"

# How much a chunk deserves to rank above its peers; tuned for search quality
# (a security finding or an endpoint is more answer-worthy than a folder).
IMPORTANCE = {
    SUMMARY: 1.0,
    SECURITY: 0.95,
    API_ENDPOINT: 0.9,
    ARCHITECTURE: 0.85,
    DATABASE: 0.8,
    FRAMEWORK: 0.8,
    DEPLOYMENT: 0.75,
    DOCKER: 0.75,
    CICD: 0.7,
    TESTING: 0.7,
    DOCUMENTATION: 0.7,
    PERFORMANCE: 0.7,
    QUALITY: 0.65,
    CUDA: 0.65,
    FILE: 0.6,
    DEPENDENCY: 0.55,
    FOLDER: 0.5,
}

# Canonical "what is this framework for" knowledge -- small, curated, stable.
_FRAMEWORK_PURPOSE: dict[str, str] = {
    "fastapi": "Python API framework for building REST services",
    "flask": "Python micro web framework for building web apps and APIs",
    "django": "Python batteries-included web framework with ORM and admin",
    "react": "JavaScript UI library for building component-based interfaces",
    "next.js": "React framework for full-stack web apps with SSR",
    "vue": "JavaScript UI framework for building component-based interfaces",
    "express": "Node.js web framework for building APIs and web servers",
    "spring boot": "Java framework for production-grade standalone services",
}

# Common dependency names -> one-line purpose. Anything not listed still gets
# a chunk -- name/version alone are still meaningful, embeddable content.
_DEPENDENCY_PURPOSE: dict[str, str] = {
    "bcrypt": "password hashing",
    "passlib": "password hashing and verification",
    "jwt": "JSON web token creation and verification",
    "pyjwt": "JSON web token creation and verification",
    "requests": "HTTP client library",
    "httpx": "async HTTP client library",
    "axios": "HTTP client library",
    "pytest": "test runner and assertions",
    "mypy": "static type checking",
    "ruff": "linting and formatting",
    "black": "code formatting",
    "fastapi": "API framework",
    "gunicorn": "WSGI HTTP server for production deployments",
    "uvicorn": "ASGI HTTP server for production deployments",
    "celery": "distributed task queue",
    "redis": "in-memory data store (cache/queue)",
    "psycopg2": "PostgreSQL database driver",
    "sqlalchemy": "SQL toolkit and ORM",
    "alembic": "database migrations",
    "jinja2": "template engine",
    "click": "CLI framework",
    "typer": "CLI framework",
}

# Folder name -> likely purpose. Shown in folder/file chunk content so the
# embedding is about meaning ("this is the API layer"), not just the name.
_FOLDER_PURPOSE: dict[str, str] = {
    "api": "HTTP API routes and request handlers",
    "app": "application entry point and wiring",
    "auth": "authentication and authorization logic",
    "config": "configuration and settings",
    "controllers": "request handlers / controllers",
    "core": "core domain logic and shared primitives",
    "db": "database models, migrations and connection setup",
    "database": "database models, migrations and connection setup",
    "docs": "documentation",
    "handlers": "request handlers",
    "lib": "library code reused across the app",
    "middleware": "request middleware / filters",
    "migrations": "database migrations",
    "models": "data models",
    "public": "static assets served to clients",
    "routes": "API route definitions",
    "scripts": "utility scripts",
    "services": "business logic / service layer",
    "src": "primary source code",
    "static": "static assets",
    "tests": "tests",
    "test": "tests",
    "utils": "small shared utilities",
    "views": "UI views / templates",
    "workers": "background workers and jobs",
}

_MAX_DEPENDENCY_CHUNKS = 15


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stable_id(repository_id: uuid.UUID, chunk_type: str, title: str) -> str:
    return hashlib.sha1(f"{repository_id}|{chunk_type}|{title}".encode()).hexdigest()


def _checksum(content: str, meta: dict) -> str:
    material = json.dumps({"content": content, "metadata": meta}, sort_keys=True)
    return hashlib.sha1(material.encode()).hexdigest()


def _purpose(name: str, table: dict[str, str]) -> str | None:
    """Case-insensitive purpose lookup; also matches 'src/app' style names."""
    key = name.lower().strip("/")
    if key in table:
        return table[key]
    for candidate, purpose in table.items():
        if key.startswith(f"{candidate}/") or key.endswith(f"/{candidate}"):
            return purpose
    return None


def _fold_sentence(items: list[str]) -> str:
    """'a, b, c' / 'a and b' -- reads better in embedded content than JSON."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


class ChunkBuilder:
    """Stateless builder: given a RepositoryKnowledge, produce the chunk list.
    Deterministic given the same input -- required for checksum-based skips.

    Two-phase: (1) build every chunk body; (2) wire relationships once all
    chunk ids are known, so edges never depend on build order.
    """

    def __init__(self, repository_id: uuid.UUID, knowledge: RepositoryKnowledge) -> None:
        self.repository_id = repository_id
        self.knowledge = knowledge
        self._chunks: list[KnowledgeChunk] = []
        self._by_title: dict[str, KnowledgeChunk] = {}
        # Pending edges recorded while chunks are built: {chunk_id: [(kind, target_title)]}.
        # Resolved in phase 2 once every target chunk id is known.
        self._pending: dict[str, list[tuple[str, str]]] = {}

    def build(self) -> list[KnowledgeChunk]:
        self._chunks = [
            *self._summary_chunk(),
            *self._architecture_chunk(),
            *self._folder_chunks(),
            *self._file_chunks(),
            *self._framework_chunks(),
            *self._database_chunks(),
            *self._api_chunks(),
            *self._dependency_chunks(),
            *self._docker_chunk(),
            *self._cuda_chunk(),
            *self._cicd_chunk(),
            *self._deployment_chunk(),
            *self._testing_chunk(),
            *self._documentation_chunk(),
            *self._performance_chunk(),
            *self._security_chunk(),
            *self._quality_chunk(),
        ]
        # Last-resort uniqueness guarantee: two chunks sharing type+title
        # would collapse into one id (and one index point). The builders
        # avoid this (endpoint titles carry their file), but if it ever
        # happens, later duplicates get a deterministic counter suffix so the
        # index stays 1:1 and checksum skips keep working across runs.
        seen: dict[str, int] = {}
        for chunk in self._chunks:
            count = seen.get(chunk.id, 0)
            seen[chunk.id] = count + 1
            if count > 0:
                chunk.id = f"{chunk.id}-{count}"
        self._by_title = {chunk.title: chunk for chunk in self._chunks}
        self._wire_relationships()
        for chunk in self._chunks:
            chunk.relationships = self._dedupe_relationships(chunk.relationships)
        return self._chunks

    def _wire_relationships(self) -> None:
        """Phase 2: resolve every recorded edge against the full chunk set."""
        for chunk_id, edges in self._pending.items():
            chunk = next(c for c in self._chunks if c.id == chunk_id)
            chunk.relationships.extend(self._rels_edges(edges))

    def _rels_edges(self, edges: list[tuple[str, str]]) -> list[ChunkRelationship]:
        rels: list[ChunkRelationship] = []
        for kind, title in edges:
            target = self._by_title.get(title)
            if target is not None:
                rels.append(
                    ChunkRelationship(
                        kind=kind,
                        target_chunk_id=target.id,
                        target_title=target.title,
                        target_type=target.type,
                    )
                )
        return rels

    def _queue_rel(self, chunk_id: str, kind: str, title: str) -> None:
        self._pending.setdefault(chunk_id, []).append((kind, title))

    # -- chunk construction -------------------------------------------------

    def _make(
        self,
        chunk_type: str,
        title: str,
        content: str,
        *,
        meta: dict | None = None,
        priority: float | None = None,
    ) -> KnowledgeChunk:
        now = _now()
        checksum = _checksum(content, meta or {})
        return KnowledgeChunk(
            id=_stable_id(self.repository_id, chunk_type, title),
            repository_id=self.repository_id,
            type=chunk_type,
            title=title,
            content=content,
            metadata=ChunkMetadata(
                repository=self.knowledge.metadata.name,
                type=chunk_type,
                importance=IMPORTANCE[chunk_type],
                confidence=1.0,
                checksum=checksum,
                version=1,
                created_at=now,
                updated_at=now,
                **(meta or {}),
            ),
            relationships=[],
            priority=priority if priority is not None else IMPORTANCE[chunk_type],
            checksum=checksum,
            version=1,
            created_at=now,
            updated_at=now,
        )

    def _rel(self, kind: str, title: str) -> ChunkRelationship | None:
        target = self._by_title.get(title)
        if target is None:
            return None
        return ChunkRelationship(
            kind=kind,
            target_chunk_id=target.id,
            target_title=target.title,
            target_type=target.type,
        )

    def _rels(self, kind: str, titles: list[str]) -> list[ChunkRelationship]:
        return [r for t in titles if (r := self._rel(kind, t)) is not None]

    @staticmethod
    def _dedupe_relationships(rels: list[ChunkRelationship]) -> list[ChunkRelationship]:
        seen: set[tuple[str, str]] = set()
        unique: list[ChunkRelationship] = []
        for rel in rels:
            key = (rel.kind, rel.target_chunk_id)
            if key in seen:
                continue
            seen.add(key)
            unique.append(rel)
        return unique

    def _lang(self) -> str | None:
        langs = self.knowledge.languages.languages
        return langs[0] if langs else None

    # -- chunk groups --------------------------------------------------------

    def _summary_chunk(self) -> list[KnowledgeChunk]:
        k = self.knowledge
        md = k.metadata
        content = (
            f"Repository Summary: {md.name or 'this repository'}. "
            f"Description: {md.description or 'none provided'}. "
            f"Type: {md.repository_type or 'unknown'}. "
            f"License: {md.license or 'unknown'}. "
            f"Primary languages: {_fold_sentence(k.languages.languages) or 'none detected'}. "
            f"Frameworks: {_fold_sentence(k.frameworks.frameworks) or 'none detected'}. "
            f"Package managers: {_fold_sentence(k.dependencies.package_managers) or 'none detected'}. "
            f"Main entry point: {md.main_entry_point or 'unknown'}. "
            f"Use cases: {_fold_sentence(k.architecture.use_cases) or 'not determined'}. "
            f"Potential applications: {_fold_sentence(k.architecture.potential_applications) or 'not determined'}."
        )
        return [self._make(SUMMARY, "Repository Summary", content)]

    def _architecture_chunk(self) -> list[KnowledgeChunk]:
        k = self.knowledge
        lines = []
        if k.architecture.summary:
            lines.append(f"Architecture overview: {k.architecture.summary}")
        if k.architecture.production_readiness:
            lines.append(f"Production readiness: {k.architecture.production_readiness}.")
        if k.architecture.difficulty_level:
            lines.append(f"Difficulty level: {k.architecture.difficulty_level}.")
        if k.architecture.folder_structure:
            top = list(k.architecture.folder_structure)[:12]
            lines.append(f"Top-level structure: {', '.join(top)}.")
        if k.metadata.main_entry_point:
            lines.append(f"Main entry point: {k.metadata.main_entry_point}.")
        if not lines:
            return []
        return [self._make(ARCHITECTURE, "Architecture Overview", " ".join(lines))]

    def _folder_chunks(self) -> list[KnowledgeChunk]:
        tree = self.knowledge.architecture.folder_structure or self.knowledge.files.folder_structure
        return self._walk_folders(tree, directory="")

    def _walk_folders(self, tree: dict, directory: str) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        for name, value in tree.items():
            is_dir = isinstance(value, dict)
            full = f"{directory}/{name}".lstrip("/")
            if not is_dir:
                continue
            children = [c for c in value if isinstance(value[c], dict)]
            files = [c for c in value if not isinstance(value[c], dict)]
            purpose = _purpose(name, _FOLDER_PURPOSE)
            lines = [
                f"Folder {full}: contains {len(children)} subfolder(s) and {len(files)} file(s)."
            ]
            if purpose:
                lines.append(f"Likely purpose: {purpose}.")
            if children:
                lines.append(f"Subfolders: {', '.join(children[:12])}.")
            chunk = self._make(FOLDER, f"Folder: {full}", " ".join(lines), meta={"directory": full})
            for child in children:
                self._queue_rel(chunk.id, "contains", f"Folder: {child}")
            for child_file in files:
                self._queue_rel(chunk.id, "contains", f"File: {full}/{child_file}")
            chunks.append(chunk)
            chunks.extend(self._walk_folders(value, full))
        return chunks

    def _file_chunks(self) -> list[KnowledgeChunk]:
        tree = self.knowledge.architecture.folder_structure or self.knowledge.files.folder_structure
        return self._walk_files(tree, directory="")

    def _endpoints(self) -> list[ApiEndpoint]:
        """Coerce plain dicts (tests, raw detector output) to ApiEndpoint
        models; pydantic does not re-validate direct attribute assignment."""
        return [
            e if isinstance(e, ApiEndpoint) else ApiEndpoint.model_validate(e)
            for e in self.knowledge.apis.endpoints
        ]

    def _walk_files(self, tree: dict, directory: str) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        endpoints = self._endpoints()
        for name, value in tree.items():
            full = f"{directory}/{name}".lstrip("/")
            if isinstance(value, dict):
                chunks.extend(self._walk_files(value, full))
                continue
            lang = self._language_for_file(name)
            purpose = _purpose(name, _FOLDER_PURPOSE)
            imports = self.knowledge.imports.dependency_graph.get(full, [])
            file_endpoints = [e for e in endpoints if self._endpoint_file(e) == full]
            lines = [f"File {full} is a {lang or 'source'} file."]
            if purpose:
                lines.append(f"Likely purpose: {purpose}.")
            if file_endpoints:
                shown = [
                    f"{self._method(e)} {e.path}" for e in file_endpoints[:10]
                ]
                lines.append(f"Defines API endpoints: {', '.join(shown)}.")
            if imports:
                lines.append(f"Imports: {', '.join(imports[:10])}.")
            chunk = self._make(
                FILE,
                f"File: {full}",
                " ".join(lines),
                meta={"directory": directory or None, "file": full, "language": lang},
            )
            for e in file_endpoints:
                self._queue_rel(
                    chunk.id,
                    "contains",
                    f"API: {self._method(e)} {e.path} ({self._endpoint_file(e)})",
                )
            for fw in self.knowledge.frameworks.frameworks:
                if fw.lower() in " ".join(imports).lower():
                    self._queue_rel(chunk.id, "uses", f"Framework: {fw}")
            chunks.append(chunk)
        return chunks

    @staticmethod
    def _method(endpoint) -> str:
        raw = endpoint.get("method") if isinstance(endpoint, dict) else endpoint.method
        return (raw or "GET").upper()

    @staticmethod
    def _endpoint_file(endpoint) -> str:
        """Detectors may record Windows-style paths on Windows; the folder
        tree (and therefore file-chunk titles) is always forward-slash.
        Tolerates plain dicts as well as pydantic ApiEndpoint objects."""
        raw = endpoint.get("file") if isinstance(endpoint, dict) else endpoint.file
        return (raw or "").replace("\\", "/")

    def _framework_chunks(self) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        for fw in self.knowledge.frameworks.frameworks:
            purpose = _FRAMEWORK_PURPOSE.get(fw.lower())
            content = f"Framework: {fw}." + (f" Purpose: {purpose}." if purpose else "")
            chunk = self._make(FRAMEWORK, f"Framework: {fw}", content, meta={"framework": fw})
            for file, imports in self.knowledge.imports.dependency_graph.items():
                if fw.lower() in " ".join(imports).lower():
                    self._queue_rel(chunk.id, "used_by", f"File: {file}")
            chunks.append(chunk)
        return chunks

    def _database_chunks(self) -> list[KnowledgeChunk]:
        k = self.knowledge
        chunks: list[KnowledgeChunk] = []
        orm_names = ", ".join(k.databases.orms) if k.databases.orms else "none detected"
        for db in k.databases.databases:
            content = (
                f"Database {db} is used by this repository. "
                f"ORM/access layer: {orm_names}. "
                f"API endpoints read and write this database."
            )
            chunks.append(self._make(DATABASE, f"Database: {db}", content, meta={"framework": db}))
        for orm in k.databases.orms:
            content = f"ORM layer: {orm} is used to access {_fold_sentence(k.databases.databases) or 'the database'}."
            chunks.append(self._make(DATABASE, f"ORM: {orm}", content))
        return chunks

    def _api_chunks(self) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        endpoints = self._endpoints()
        for endpoint in endpoints:
            method = self._method(endpoint)
            path = endpoint.path or ""
            file = self._endpoint_file(endpoint)
            auth = "yes" if any(token in path.lower() for token in ("login", "auth", "token", "password", "oauth", "register")) else "no"
            lines = [
                f"API endpoint {method} {path} is defined in {file}.",
                f"Likely requires authentication: {auth}.",
            ]
            # The file goes into the title so chunks stay unique: the same
            # route (e.g. "GET /") can legitimately exist in several files
            # (a test suite re-defining a route, a v1/v2 layout, ...) and
            # identical type+title would collapse into one chunk id.
            chunks.append(
                self._make(
                    API_ENDPOINT,
                    f"API: {method} {path} ({file})",
                    " ".join(lines),
                    meta={"file": file, "symbol": f"{method} {path}", "language": self._lang()},
                )
            )
            chunk = chunks[-1]
            self._queue_rel(chunk.id, "defined_in", f"File: {file}")
            for db in self.knowledge.databases.databases:
                self._queue_rel(chunk.id, "uses", f"Database: {db}")
        return chunks

    def _dependency_chunks(self) -> list[KnowledgeChunk]:
        k = self.knowledge
        chunks: list[KnowledgeChunk] = []
        # Cap the count: dependencies are informational, not the search target.
        for name, version in list(k.dependencies.dependencies.items())[:_MAX_DEPENDENCY_CHUNKS]:
            purpose = _DEPENDENCY_PURPOSE.get(name.lower())
            if purpose:
                content = f"Dependency {name} ({version or 'any version'}) is used for {purpose}."
            else:
                content = f"Dependency {name} ({version or 'any version'}) is a declared dependency."
            chunk = self._make(DEPENDENCY, f"Dependency: {name}", content, meta={"framework": name})
            for fw in k.frameworks.frameworks:
                if fw.lower() == name.lower():
                    self._queue_rel(chunk.id, "is", f"Framework: {fw}")
            chunks.append(chunk)
        return chunks

    def _docker_chunk(self) -> list[KnowledgeChunk]:
        k = self.knowledge
        if not k.docker.docker_support:
            return []
        lines = [
            "Docker is supported.",
            f"Dockerfile: {k.docker.dockerfile_path or 'not detected'}.",
        ]
        if k.docker.compose_services:
            lines.append(f"Docker Compose services: {', '.join(k.docker.compose_services)}.")
        return [self._make(DOCKER, "Docker Support", " ".join(lines))]

    def _cuda_chunk(self) -> list[KnowledgeChunk]:
        k = self.knowledge
        if k.cuda.gpu_required is None and k.cuda.cuda_required is None:
            return []
        lines = [
            f"GPU required: {'yes' if k.cuda.gpu_required else 'no' if k.cuda.gpu_required is not None else 'unknown'}.",
            f"CUDA required: {'yes' if k.cuda.cuda_required else 'no' if k.cuda.cuda_required is not None else 'unknown'}.",
        ]
        return [self._make(CUDA, "CUDA/GPU Requirements", " ".join(lines))]

    def _cicd_chunk(self) -> list[KnowledgeChunk]:
        k = self.knowledge
        lines = []
        if k.cicd.providers:
            lines.append(f"CI/CD providers: {', '.join(k.cicd.providers)}.")
        if k.cicd.workflow_files:
            lines.append(f"Workflow files: {', '.join(k.cicd.workflow_files[:8])}.")
        if not lines:
            return []
        return [self._make(CICD, "CI/CD Pipelines", " ".join(lines))]

    def _deployment_chunk(self) -> list[KnowledgeChunk]:
        k = self.knowledge
        if not k.deployment.platforms:
            return []
        content = f"Deployment targets: {', '.join(k.deployment.platforms)}."
        return [self._make(DEPLOYMENT, "Deployment", content)]

    def _testing_chunk(self) -> list[KnowledgeChunk]:
        k = self.knowledge
        lines = [
            f"Tests present: {'yes' if k.testing.has_tests else 'no'}.",
            f"Test files: {k.testing.test_file_count}.",
        ]
        if k.testing.frameworks:
            lines.append(f"Testing frameworks: {', '.join(k.testing.frameworks)}.")
        return [self._make(TESTING, "Testing", " ".join(lines))]

    def _documentation_chunk(self) -> list[KnowledgeChunk]:
        k = self.knowledge
        lines = [
            f"README present: {'yes' if k.documentation.has_readme else 'no'}.",
            f"Contributing guide: {'yes' if k.documentation.has_contributing else 'no'}.",
            f"License file: {'yes' if k.documentation.has_license_file else 'no'}.",
        ]
        if k.documentation.installation_steps:
            lines.append(f"Installation steps: {' | '.join(k.documentation.installation_steps[:6])}.")
        return [self._make(DOCUMENTATION, "Documentation", " ".join(lines))]

    def _performance_chunk(self) -> list[KnowledgeChunk]:
        k = self.knowledge
        if not k.performance.notes:
            return []
        content = f"Performance notes: {' '.join(k.performance.notes[:8])}."
        return [self._make(PERFORMANCE, "Performance Notes", content)]

    def _security_chunk(self) -> list[KnowledgeChunk]:
        k = self.knowledge
        findings = k.security.findings
        if not findings:
            return [
                self._make(
                    SECURITY,
                    "Security Considerations",
                    "No security findings detected by static analysis.",
                )
            ]
        content = "Security considerations: " + "; ".join(findings[:10]) + "."
        return [self._make(SECURITY, "Security Considerations", content)]

    def _quality_chunk(self) -> list[KnowledgeChunk]:
        k = self.knowledge
        content = (
            f"Code quality snapshot: {k.quality.total_files} files, {k.quality.total_lines} "
            f"lines of code, {k.quality.todo_count} TODO/FIXME markers."
        )
        return [self._make(QUALITY, "Code Quality", content)]

    @staticmethod
    def _language_for_file(filename: str) -> str | None:
        mapping = {
            ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript",
            ".tsx": "TypeScript", ".java": "Java", ".go": "Go", ".rs": "Rust", ".c": "C",
            ".cpp": "C++", ".h": "C/C++ header", ".rb": "Ruby", ".php": "PHP", ".cs": "C#",
            ".swift": "Swift", ".kt": "Kotlin", ".scala": "Scala", ".html": "HTML",
            ".css": "CSS", ".scss": "SCSS", ".sql": "SQL", ".sh": "Shell", ".yaml": "YAML",
            ".yml": "YAML", ".json": "JSON", ".md": "Markdown", ".toml": "TOML",
        }
        for suffix, language in mapping.items():
            if filename.endswith(suffix):
                return language
        return None


def build_knowledge_chunks(
    repository_id: uuid.UUID, knowledge: RepositoryKnowledge
) -> list[KnowledgeChunk]:
    """Public entry point -- deterministic chunk list for one repository."""
    return ChunkBuilder(repository_id, knowledge).build()
