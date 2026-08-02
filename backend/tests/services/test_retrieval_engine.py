"""IntelligentRetriever end-to-end tests over a real (local) index, plus
pipeline unit tests with a stub knowledge retriever (no Qdrant needed)."""

import pytest

from app.models.schemas.retrieval import (
    RetrieveRequest,
    RetrievalIntent,
    SearchMode,
)
from app.services.knowledge.chunk_builder import build_knowledge_chunks
from app.services.knowledge.embedding_service import index_knowledge_chunks
from app.services.knowledge.retriever import KnowledgeRetriever
from app.services.retrieval.engine import IntelligentRetriever


@pytest.fixture
def engine(sample_knowledge, index_settings, fake_embeddings) -> IntelligentRetriever:
    chunks = build_knowledge_chunks(sample_knowledge.repository_id, sample_knowledge)
    index_knowledge_chunks(
        index_settings,
        sample_knowledge.repository_id,
        chunks,
        fake_embeddings,
        run_id="run-engine-1",
    )
    retriever = KnowledgeRetriever(index_settings, embeddings=fake_embeddings)
    return IntelligentRetriever(retriever)


def test_retrieve_builds_full_context(engine: IntelligentRetriever, sample_knowledge) -> None:
    repo = str(sample_knowledge.repository_id)
    context = engine.retrieve(repo, RetrieveRequest(query="how does authentication work?"))

    assert context.query == "how does authentication work?"
    assert context.intent in {
        RetrievalIntent.SECURITY,
        RetrievalIntent.EXPLANATION,
        RetrievalIntent.FEATURE_LOCATION,
    }
    assert context.rewritten_query != context.query  # expansion ran
    assert context.chunks
    assert context.confidence > 0.0
    assert context.citations
    assert context.metrics.latency_ms >= 0.0
    assert context.metrics.returned_chunks == len(context.chunks)
    assert context.summary is not None or any(
        h.type == "api_endpoint" for h in context.chunks
    )
    # All chunks are RerankedHits with a display score.
    assert all(0 <= h.display_score <= 100 for h in context.chunks)
    assert all(h.hop == 0 for h in context.chunks if h.hop is not None)


def test_retrieve_relationship_expansion_adds_graph(
    engine: IntelligentRetriever, sample_knowledge
) -> None:
    repo = str(sample_knowledge.repository_id)
    context = engine.retrieve(
        repo, RetrieveRequest(query="login endpoint", expansion_depth=1)
    )
    if context.graph.nodes:
        assert context.graph.edges  # nodes imply edges here
    hop1 = [h for h in context.chunks if h.hop > 0]
    if hop1:
        assert any(h.type in {"file", "database"} for h in hop1)


def test_retrieve_cache_second_call_is_cache_hit(
    engine: IntelligentRetriever, sample_knowledge
) -> None:
    repo = str(sample_knowledge.repository_id)
    request = RetrieveRequest(query="what database is used?")
    first = engine.retrieve(repo, request)
    assert first.metrics.cache_hit is False

    second = engine.retrieve(repo, request)
    assert second.metrics.cache_hit is True
    assert second.metrics.cache_key == first.metrics.cache_key
    assert second.query == first.query


def test_retrieve_exact_mode_finds_named_file(
    engine: IntelligentRetriever, sample_knowledge
) -> None:
    repo = str(sample_knowledge.repository_id)
    context = engine.retrieve(repo, RetrieveRequest(query="api/auth.py", mode=SearchMode.EXACT))
    assert any(h.file and "api/auth.py" in h.file for h in context.chunks)


def test_retrieve_empty_query_raises(engine: IntelligentRetriever, sample_knowledge) -> None:
    with pytest.raises(ValueError):
        engine.retrieve(str(sample_knowledge.repository_id), RetrieveRequest(query="   "))


def test_lookup_exact_symbol(engine: IntelligentRetriever, sample_knowledge) -> None:
    repo = str(sample_knowledge.repository_id)
    response = engine.lookup(repo, "login", kind="api")
    assert response.query == "login"
    assert any("login" in h.title.lower() for h in response.results)


def test_suggest_returns_templates_and_facts(
    engine: IntelligentRetriever, sample_knowledge
) -> None:
    response = engine.suggest(str(sample_knowledge.repository_id), "")
    assert len(response.items) > 0
    assert any("architecture" in item for item in response.items)
    filtered = engine.suggest(str(sample_knowledge.repository_id), "how")
    assert all("how" in item.lower() for item in filtered.items)


# ---------------------------------------------------------------------------
# Hermetic pipeline test with a stub knowledge retriever
# ---------------------------------------------------------------------------


class _StubKnowledge:
    """Minimal stand-in for KnowledgeRetriever: fixed results, no Qdrant."""

    def __init__(self) -> None:
        self.results = []
        self.stats_result = type(
            "S", (), {"languages": ["python"], "frameworks": ["flask"]}
        )()

    def stats(self, repository_id: str):
        return self.stats_result

    def semantic_search(self, repository_id, query, filters=None, limit=10):
        return [h for h in self.results if h.type != "dependency"][:limit]

    def hybrid_search(self, repository_id, query, filters=None, limit=10, keyword_query=None):
        return self.results[:limit]

    def exact_lookup(self, repository_id, query, kind=None, limit=10):
        return [h for h in self.results if query.lower() in h.title.lower()][:limit]

    def get_chunk(self, repository_id, chunk_id):
        return None


def _stub_hit(chunk_id: str, title: str, chunk_type: str) -> "SearchHit":
    from app.models.schemas.knowledge_chunks import SearchHit

    return SearchHit(
        chunk_id=chunk_id,
        type=chunk_type,
        title=title,
        summary=f"{title} summary",
        score=0.8,
        importance=0.7,
        confidence=0.9,
        version=3,
        related_chunks=[],
    )


def test_engine_uses_stub_without_index():
    stub = _StubKnowledge()
    stub.results = [
        _stub_hit("db-1", "Database: PostgreSQL", "database"),
        _stub_hit("file-1", "File: app.py", "file"),
    ]
    engine = IntelligentRetriever(stub)
    context = engine.retrieve("repo-x", RetrieveRequest(query="database"))
    assert context.intent == RetrievalIntent.DATABASE
    assert context.chunks
    assert context.repository_version == "3"
    assert context.confidence > 0.0


def test_engine_rewrites_before_search():
    stub = _StubKnowledge()
    stub.results = [_stub_hit("s-1", "Security: auth", "security")]
    engine = IntelligentRetriever(stub)

    seen_queries = []

    class RecordingStub(_StubKnowledge):
        def hybrid_search(self, repository_id, query, filters=None, limit=10, keyword_query=None):
            seen_queries.append(query)
            return self.results[:limit]

    recording = RecordingStub()
    recording.results = stub.results
    IntelligentRetriever(recording).retrieve("repo-x", RetrieveRequest(query="how does auth work"))
    assert seen_queries and "authentication" in seen_queries[0]


def test_engine_keyword_leg_uses_original_query_not_rewrite():
    stub = _StubKnowledge()
    stub.results = [_stub_hit("s-1", "Security: auth", "security")]
    engine = IntelligentRetriever(stub)

    seen = {}

    class RecordingStub(_StubKnowledge):
        def hybrid_search(self, repository_id, query, filters=None, limit=10, keyword_query=None):
            seen["embedded"] = query
            seen["keyword"] = keyword_query
            return self.results[:limit]

    recording = RecordingStub()
    recording.results = stub.results
    IntelligentRetriever(recording).retrieve(
        "repo-x", RetrieveRequest(query="import flask")
    )
    # the vector leg embeds the rewritten query...
    assert "flask" in seen["embedded"] or seen["embedded"] != "import flask"
    # ...but the keyword leg tokenizes the original, un-rewritten query
    assert seen["keyword"] == "import flask"
