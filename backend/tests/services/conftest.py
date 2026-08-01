"""Shared fixtures for the Semantic Knowledge Index tests.

The index/retriever tests talk to the same Qdrant backend the app uses (env
config: remote URL or local mode) but under a uniquely named collection per
test, deleted at teardown -- so they never touch `repomind_chunks`.

Embeddings are a deterministic token-overlap hash: identical text -> identical
vector (cosine 1.0), shared words -> non-zero cosine. That's enough to make
"search for the database chunk" actually rank the database chunk first
without any model or network.
"""

import hashlib
import re
import uuid

import pytest
from langchain_core.embeddings import Embeddings

from app.ai.vectorstore.qdrant_store import get_qdrant_client
from app.core.config import Settings
from app.models.schemas.knowledge import RepositoryKnowledge

_TOKEN_RE = re.compile(r"[a-z0-9_]{2,}")
_EMBEDDING_DIM = 4096

# Each distinct token gets its own dimension (no collisions, deterministic
# rankings: identical text -> cosine 1.0, shared words -> proportional cosine).
_TOKEN_INDEX: dict[str, int] = {}


def _token_dim(token: str) -> int:
    if token not in _TOKEN_INDEX:
        _TOKEN_INDEX[token] = len(_TOKEN_INDEX) % _EMBEDDING_DIM
    return _TOKEN_INDEX[token]


class FakeEmbeddings(Embeddings):
    """Deterministic, local, token-overlap embeddings (no network/model)."""

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * _EMBEDDING_DIM
        for token in _TOKEN_RE.findall(text.lower()):
            vector[_token_dim(token)] += 1.0
        norm = sum(v * v for v in vector) ** 0.5
        return [v / norm if norm else 0.0 for v in vector]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]


@pytest.fixture
def fake_embeddings() -> FakeEmbeddings:
    return FakeEmbeddings()


@pytest.fixture
def index_settings() -> Settings:
    """Settings pointing at a throwaway collection name, cleaned up after."""
    name = f"test_knowledge_{uuid.uuid4().hex[:10]}"
    settings = Settings(qdrant_collection_name=name)
    yield settings
    try:
        get_qdrant_client().delete_collection(name)
    except Exception:
        pass


@pytest.fixture
def sample_knowledge() -> RepositoryKnowledge:
    """A small but multi-faceted knowledge report: Flask + PostgreSQL + a
    login endpoint + one folder tree with an api/ folder and a couple of
    files -- enough to produce summary, architecture, folder, file, api,
    database, framework, dependency, security and quality chunks."""
    return RepositoryKnowledge(
        repository_id=uuid.uuid4(),
        metadata={
            "name": "sample-app",
            "description": "A sample Flask API with auth",
            "repository_type": "application",
            "license": "MIT",
            "main_entry_point": "app.py",
        },
        languages={"languages": ["Python"], "stats": [{"name": "Python", "file_count": 3}]},
        frameworks={"frameworks": ["Flask"]},
        dependencies={"dependencies": {"flask": "3.0.0", "bcrypt": "4.1.0"}, "package_managers": ["pip"]},
        architecture={
            "summary": "A small Flask API service with a login endpoint and a PostgreSQL store.",
            "folder_structure": {
                "app.py": None,
                "api": {"routes.py": None, "auth.py": None},
            },
            "production_readiness": "early prototype",
            "difficulty_level": "beginner",
            "use_cases": ["user authentication"],
            "potential_applications": ["small web service"],
        },
        files={"total_files": 3, "folder_structure": {"app.py": None, "api": {"routes.py": None, "auth.py": None}}},
        symbols={"total_symbols": 4},
        imports={
            "dependency_graph": {
                "app.py": ["flask"],
                "api/routes.py": ["flask"],
                "api/auth.py": ["flask", "bcrypt"],
            }
        },
        apis={
            "endpoints": [
                {"method": "POST", "path": "/login", "file": "api/auth.py"},
                {"method": "GET", "path": "/health", "file": "api/routes.py"},
            ]
        },
        databases={"databases": ["PostgreSQL"], "orms": ["SQLAlchemy"]},
        docker={"docker_support": False},
        cuda={"gpu_required": False, "cuda_required": False},
        cicd={"providers": [], "workflow_files": []},
        deployment={"platforms": []},
        testing={"frameworks": ["pytest"], "has_tests": True, "test_file_count": 2},
        documentation={"has_readme": True, "installation_steps": ["pip install -r requirements.txt"]},
        performance={"notes": []},
        security={"findings": ["hardcoded secret detected in api/auth.py"]},
        quality={"total_files": 3, "total_lines": 120, "todo_count": 1},
    )
