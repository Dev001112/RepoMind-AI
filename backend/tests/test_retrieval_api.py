"""API tests for the intelligent retrieval endpoints (Phase 3.3).

These use the real app via TestClient, an injected FakeEmbeddings (so no
network/model is touched), and a repository row in the dev DB with cleanup.
The vector index is only *read*: the test repo id never exists in it, so
retrieval deterministically returns an empty-but-valid context.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from langchain_core.embeddings import Embeddings

from app.database.session import SessionLocal
from app.main import app
from app.models.orm.repository import Repository
from app.models.orm.retrieval import RetrievalQueryRecord
from app.services.knowledge.retriever import KnowledgeRetriever
from app.services.retrieval.engine import IntelligentRetriever

pytestmark = pytest.mark.usefixtures("_cleanup_rows")

_created_repo_ids: list[uuid.UUID] = []
_created_query_ids: list[uuid.UUID] = []


class _FakeEmbeddings(Embeddings):
    """Never called for a repo with no indexed chunks, but must exist."""

    def embed_query(self, text: str) -> list[float]:
        return [0.0] * 4

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 4 for _ in texts]


def _make_repo() -> uuid.UUID:
    db = SessionLocal()
    try:
        repo = Repository(source_url=f"https://example.com/test-{uuid.uuid4().hex[:8]}.git")
        db.add(repo)
        db.commit()
        db.refresh(repo)
        _created_repo_ids.append(repo.id)
        return repo.id
    finally:
        db.close()


def _teardown() -> None:
    db = SessionLocal()
    try:
        for repo_id in _created_repo_ids:
            db.query(RetrievalQueryRecord).filter(
                RetrievalQueryRecord.repository_id == repo_id
            ).delete()
            db.query(Repository).filter(Repository.id == repo_id).delete()
        for query_id in _created_query_ids:
            db.query(RetrievalQueryRecord).filter(
                RetrievalQueryRecord.id == query_id
            ).delete()
        db.commit()
    finally:
        db.close()
    _created_repo_ids.clear()
    _created_query_ids.clear()


@pytest.fixture
def _cleanup_rows():
    yield
    _teardown()


@pytest.fixture
def client() -> TestClient:
    from app.api import deps as api_deps
    from tests.services.conftest import FakeEmbeddings as _ConftestFake

    app.dependency_overrides[api_deps.get_embeddings] = lambda: _ConftestFake()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_retrieve_unknown_repository_404(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/repositories/{uuid.uuid4()}/retrieve",
        json={"query": "how does auth work"},
    )
    assert response.status_code == 404


def test_retrieve_empty_query_400(client: TestClient) -> None:
    repo_id = _make_repo()
    response = client.post(
        f"/api/v1/repositories/{repo_id}/retrieve",
        json={"query": "   "},
    )
    assert response.status_code == 400


def test_retrieve_returns_context_shape(client: TestClient) -> None:
    repo_id = _make_repo()
    response = client.post(
        f"/api/v1/repositories/{repo_id}/retrieve",
        json={"query": "how does authentication work?"},
    )
    assert response.status_code == 200
    context = response.json()["context"]
    assert context["query"] == "how does authentication work?"
    assert context["intent"] in {"security", "explanation", "feature_location"}
    assert context["chunks"] == []  # repo has no indexed chunks
    assert context["confidence"] > 0.0
    assert context["metrics"]["latencyMs"] >= 0.0


def test_search_endpoint_records_history(client: TestClient) -> None:
    repo_id = _make_repo()
    response = client.post(
        f"/api/v1/repositories/{repo_id}/search/intelligent",
        json={"query": "what database is used?"},
    )
    assert response.status_code == 200
    history = client.get(f"/api/v1/repositories/{repo_id}/history")
    assert history.status_code == 200
    body = history.json()
    assert body["total"] >= 1
    assert body["items"][0]["query"] == "what database is used?"
    assert body["items"][0]["intent"] == "database"


def test_lookup_returns_200(client: TestClient) -> None:
    repo_id = _make_repo()
    response = client.post(
        f"/api/v1/repositories/{repo_id}/lookup",
        json={"query": "login", "kind": "api"},
    )
    assert response.status_code == 200
    assert response.json()["results"] == []


def test_suggestions_returns_templates(client: TestClient) -> None:
    repo_id = _make_repo()
    response = client.get(f"/api/v1/repositories/{repo_id}/suggestions")
    assert response.status_code == 200
    assert response.json()["items"]


def test_history_empty_for_fresh_repo(client: TestClient) -> None:
    repo_id = _make_repo()
    response = client.get(f"/api/v1/repositories/{repo_id}/history")
    assert response.status_code == 200
    assert response.json() == {"total": 0, "items": []}


def test_metrics_aggregate_from_records(client: TestClient) -> None:
    repo_id = _make_repo()
    db = SessionLocal()
    try:
        for cache_hit in (True, False):
            record = RetrievalQueryRecord(
                repository_id=repo_id,
                query="q",
                intent="api",
                mode="hybrid",
                latency_ms=12.0,
                chunk_count=3,
                cache_hit=cache_hit,
                quality_score=0.5,
            )
            db.add(record)
            db.flush()
            _created_query_ids.append(record.id)
        db.commit()
    finally:
        db.close()

    response = client.get(f"/api/v1/repositories/{repo_id}/retrieval/metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["totalQueries"] == 2
    assert float(body["avgLatencyMs"]) == 12.0
    assert body["cacheHitRate"] == 0.5
    assert body["topIntents"] == [{"intent": "api", "count": 2}]


def test_engine_instantiation_smoke() -> None:
    # The endpoint wiring must keep working when the embeddings override
    # disappears: construct the engine exactly like the endpoint does.
    from app.core.config import get_settings

    engine = IntelligentRetriever(KnowledgeRetriever(get_settings(), embeddings=_FakeEmbeddings()))
    assert engine.knowledge is not None
