"""Relationship expansion, reranker, compressor and cache tests -- all
hermetic (dict-backed stubs, no Qdrant)."""

from app.models.schemas.knowledge_chunks import ChunkDetail, ChunkFilters
from app.models.schemas.retrieval import RerankedHit, SearchMode
from app.services.retrieval.cache import RetrievalCache
from app.services.retrieval.compressor import ContextCompressor
from app.services.retrieval.relationship import RelationshipExpander
from app.services.retrieval.reranker import ContextReranker


def _hit(
    chunk_id: str,
    title: str,
    chunk_type: str,
    score: float = 0.5,
    hop: int = 0,
    display_score: float = 0.0,
) -> RerankedHit:
    return RerankedHit(
        chunk_id=chunk_id,
        type=chunk_type,
        title=title,
        summary=f"{title} summary text",
        score=score,
        importance=0.7,
        confidence=0.8,
        version=1,
        related_chunks=[],
        display_score=display_score,
        hop=hop,
    )


def _detail(chunk_id: str, title: str, chunk_type: str, rels: list[tuple[str, str, str]]) -> ChunkDetail:
    return ChunkDetail(
        chunk_id=chunk_id,
        type=chunk_type,
        title=title,
        content=f"{title} content",
        importance=0.7,
        confidence=0.8,
        version=1,
        relationships=[
            {"kind": kind, "target_chunk_id": tid, "target_title": ttitle, "target_type": ttype}
            for kind, tid, ttitle, ttype in rels
        ],
    )


class _GraphStore:
    def __init__(self) -> None:
        self.chunks = {
            "api-1": _detail("api-1", "API: POST /login (api/auth.py)", "api_endpoint",
                             [("implemented_by", "file-1", "File: api/auth.py", "file"),
                              ("uses", "db-1", "Database: PostgreSQL", "database")]),
            "file-1": _detail("file-1", "File: api/auth.py", "file",
                              [("uses", "db-1", "Database: PostgreSQL", "database")]),
            "db-1": _detail("db-1", "Database: PostgreSQL", "database", []),
            "unrelated-1": _detail("unrelated-1", "File: api/routes.py", "file", []),
        }

    def get_chunk(self, chunk_id: str) -> ChunkDetail | None:
        return self.chunks.get(chunk_id)


def test_expansion_walks_one_hop_and_builds_graph():
    store = _GraphStore()
    seeds = [_hit("api-1", "API: POST /login (api/auth.py)", "api_endpoint", hop=0)]
    result = RelationshipExpander(store.get_chunk).expand(seeds, depth=1)

    assert result.count == 2
    ids = {h.chunk_id for h in result.expanded_hits}
    assert ids == {"file-1", "db-1"}
    assert all(h.hop == 1 for h in result.expanded_hits)
    assert len(result.edges) == 2
    assert len(result.nodes) == 3  # seed + two neighbors
    hops = {n.id: n.hop for n in result.nodes}
    assert hops["api-1"] == 0
    assert hops["file-1"] == 1


def test_expansion_depth_two_reaches_second_hop():
    store = _GraphStore()
    seeds = [_hit("api-1", "API: POST /login (api/auth.py)", "api_endpoint", hop=0)]
    result = RelationshipExpander(store.get_chunk).expand(seeds, depth=2)
    ids = {h.chunk_id for h in result.expanded_hits}
    assert "db-1" in ids
    assert "file-1" in ids


def test_expansion_dedupes_shared_neighbors():
    store = _GraphStore()
    seeds = [_hit("api-1", "API: POST /login (api/auth.py)", "api_endpoint", hop=0),
             _hit("file-1", "File: api/auth.py", "file", hop=0)]
    result = RelationshipExpander(store.get_chunk).expand(seeds, depth=1)
    ids = [n.id for n in result.nodes]
    assert ids.count("db-1") == 1  # shared neighbor visited once


def test_reranker_orders_by_score_with_type_boost():
    hits = [
        _hit("a", "Database: PostgreSQL", "database", score=0.9),
        _hit("b", "File: api/auth.py", "file", score=0.7),
    ]
    reranked = ContextReranker().rerank(hits, target_types=["database"])
    assert reranked[0].chunk_id == "a"
    assert reranked[0].display_score > reranked[1].display_score


def test_reranker_hop_discounts_expanded_hits():
    direct = _hit("d", "Direct", "file", score=0.6, hop=0)
    expanded = _hit("e", "Expanded", "file", score=0.6, hop=2)
    reranked = ContextReranker().rerank([direct, expanded], target_types=["file"])
    assert reranked[0].chunk_id == "d"


def test_compressor_dedupes_and_sections():
    hits = [
        _hit("1", "API: POST /login (api/auth.py)", "api_endpoint"),
        _hit("1", "API: POST /login (api/auth.py)", "api_endpoint"),  # duplicate
        _hit("2", "File: api/auth.py", "file"),
        _hit("3", "Database: PostgreSQL", "database"),
        _hit("4", "Security: hardcoded secret", "security"),
    ]
    result = ContextCompressor(budget=10_000).compress(hits)
    ids = [h.chunk_id for h in result.chunks]
    assert len(ids) == len(set(ids))  # deduped
    assert ids[0] == "2"  # files sectioned before apis


def test_compressor_collapses_identical_knowledge_across_distinct_ids():
    # 17 route chunks registering GET / across 17 test files -- different ids,
    # same knowledge. The compressor should collapse them to one row.
    hits = [
        _hit(f"endpoint-file{i}", "API: GET /", "api_endpoint", score=0.5)
        for i in range(17)
    ]
    hits.append(_hit("login-1", "API: GET /login (api/auth.py)", "api_endpoint", score=0.9))
    result = ContextCompressor(budget=10_000).compress(hits)
    ids = [h.chunk_id for h in result.chunks]
    # 17 identical GET / rows collapsed to 1, plus the distinct login endpoint
    assert len(ids) == 2
    assert "login-1" in ids
    assert result.dropped == 0
    assert result.collapsed == 16


def test_compressor_keeps_best_scoring_copy_when_collapsing():
    hits = [
        _hit("a1", "API: GET / (tests/a)", "api_endpoint", display_score=30),
        _hit("a2", "API: GET / (tests/a)", "api_endpoint", display_score=90),
        _hit("a3", "API: GET / (tests/a)", "api_endpoint", display_score=60),
    ]
    result = ContextCompressor(budget=10_000).compress(hits)
    assert len(result.chunks) == 1
    assert result.chunks[0].chunk_id == "a2"
    assert result.collapsed == 2


def test_content_key_differentiates_genuinely_different_chunks():
    hits = [
        _hit("e1", "API: GET /login (api/auth.py)", "api_endpoint", score=0.9),
        _hit("e2", "API: GET /add (api/route.py)", "api_endpoint", score=0.9),
    ]
    result = ContextCompressor(budget=10_000).compress(hits)
    assert len(result.chunks) == 2
    assert result.collapsed == 0


def test_compressor_budget_trims_low_sections():
    hits = [_hit(f"c{i}", f"Chunk {i}", "file", score=0.5) for i in range(20)]
    result = ContextCompressor(budget=60).compress(hits)
    assert 0 < len(result.chunks) < len(hits)
    assert result.dropped == len(hits) - len(result.chunks)
    assert result.ratio > 1.0


def test_compressor_stitches_summary_from_architecture():
    hits = [
        _hit("1", "Architecture: overview", "architecture"),
        _hit("2", "File: app.py", "file"),
    ]
    result = ContextCompressor().compress(hits)
    assert result.summary is not None
    assert "Architecture: overview" in result.summary


def test_cache_hit_and_miss():
    cache = RetrievalCache(ttl_seconds=60)
    key = cache.make_key("repo-1", "How does auth work", SearchMode.HYBRID, None, 10, 1, None)
    assert cache.get(key) is None
    cache.set(key, {"value": 42})
    assert cache.get(key) == {"value": 42}
    assert cache.stats()["hits"] == 1
    assert cache.stats()["misses"] == 1


def test_cache_key_changes_with_query_or_filters():
    cache = RetrievalCache()
    k1 = cache.make_key("repo-1", "auth", SearchMode.HYBRID, None, 10, 1, None)
    k2 = cache.make_key("repo-1", "auth login", SearchMode.HYBRID, None, 10, 1, None)
    k3 = cache.make_key("repo-1", "auth", SearchMode.HYBRID, ChunkFilters(type="security"), 10, 1, None)
    assert k1 != k2
    assert k1 != k3


def test_cache_ttl_expires_entries():
    cache = RetrievalCache(ttl_seconds=0.05)
    key = "k"
    cache.set(key, 1)
    import time
    time.sleep(0.1)
    assert cache.get(key) is None
