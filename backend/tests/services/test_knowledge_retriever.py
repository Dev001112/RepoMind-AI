"""Retriever tests: semantic / hybrid / context search, filters, and the
index-read endpoints (list, stats, single chunk) over an indexed repository.

Uses the deterministic token-overlap FakeEmbeddings from conftest, so
"what database does this use" genuinely ranks the Database chunk above
everything else -- same token vocabulary = higher cosine.
"""

import pytest

from app.models.schemas.knowledge_chunks import ChunkFilters
from app.services.knowledge.chunk_builder import build_knowledge_chunks
from app.services.knowledge.embedding_service import index_knowledge_chunks
from app.services.knowledge.retriever import KnowledgeRetriever


@pytest.fixture
def retriever(sample_knowledge, index_settings, fake_embeddings) -> KnowledgeRetriever:
    chunks = build_knowledge_chunks(sample_knowledge.repository_id, sample_knowledge)
    index_knowledge_chunks(
        index_settings,
        sample_knowledge.repository_id,
        chunks,
        fake_embeddings,
        run_id="run-1",
    )
    return KnowledgeRetriever(index_settings, embeddings=fake_embeddings)


def test_semantic_search_ranks_the_matching_knowledge_first(
    retriever: KnowledgeRetriever, sample_knowledge
) -> None:
    hits = retriever.semantic_search(str(sample_knowledge.repository_id), "what database does this use")
    assert hits, "expected at least one hit"
    assert hits[0].title == "Database: PostgreSQL"
    assert hits[0].type == "database"
    assert hits[0].file is None  # knowledge hit, not a file chunk
    assert hits[0].summary  # preview text, not raw source


def test_semantic_search_respects_metadata_filters(
    retriever: KnowledgeRetriever, sample_knowledge
) -> None:
    repo = str(sample_knowledge.repository_id)
    hits = retriever.semantic_search(
        repo, "auth", filters=ChunkFilters(type="api_endpoint"), limit=20
    )
    assert hits
    assert all(hit.type == "api_endpoint" for hit in hits)
    assert any("login" in hit.title.lower() for hit in hits)

    # A filter that matches nothing is an empty result, not an error.
    assert retriever.semantic_search(repo, "anything", filters=ChunkFilters(framework="React")) == []


def test_hybrid_search_fuses_keyword_and_vector(
    retriever: KnowledgeRetriever, sample_knowledge
) -> None:
    repo = str(sample_knowledge.repository_id)
    hits = retriever.hybrid_search(repo, "database postgresql")
    assert hits
    assert hits[0].title == "Database: PostgreSQL"

    # Exact keyword present in only one chunk surfaces it even when the
    # vector score would be middling.
    hits = retriever.hybrid_search(repo, "bcrypt password hashing")
    assert hits
    assert hits[0].type == "dependency"


def test_hybrid_without_keywords_falls_back_to_semantic(
    retriever: KnowledgeRetriever, sample_knowledge
) -> None:
    hits = retriever.hybrid_search(str(sample_knowledge.repository_id), "zz")
    assert retriever.semantic_search(str(sample_knowledge.repository_id), "zz") == hits


def test_context_search_expands_along_relationships(
    retriever: KnowledgeRetriever, sample_knowledge
) -> None:
    hits = retriever.context_search(str(sample_knowledge.repository_id), "login", limit=3)
    titles = {hit.title for hit in hits}
    assert any(title.startswith("API: POST /login") for title in titles)
    # One hop: the endpoint's defining file and the database it uses.
    assert any(title.startswith("File:") for title in titles)
    assert any(title.startswith("Database:") for title in titles)


def test_list_chunks_paginates_and_counts(
    retriever: KnowledgeRetriever, sample_knowledge
) -> None:
    repo = str(sample_knowledge.repository_id)
    page1, total = retriever.list_chunks(repo, page_size=5)
    page2, _ = retriever.list_chunks(repo, page=2, page_size=5)
    assert total >= 10
    assert len(page1) == 5
    assert len(page2) == 5
    assert {item.chunk_id for item in page1}.isdisjoint({item.chunk_id for item in page2})

    api_only, api_total = retriever.list_chunks(repo, chunk_type="api_endpoint")
    assert api_total == 2
    assert all(item.type == "api_endpoint" for item in api_only)


def test_stats_aggregate_categories(retriever: KnowledgeRetriever, sample_knowledge) -> None:
    stats = retriever.stats(str(sample_knowledge.repository_id))
    assert stats is not None
    assert stats.total_chunks >= 10
    categories = {c["type"]: c["count"] for c in stats.categories}
    assert categories.get("api_endpoint") == 2
    assert "Python" in stats.languages
    assert "Flask" in stats.frameworks
    assert stats.files >= 3


def test_get_chunk_returns_detail_and_edges(
    retriever: KnowledgeRetriever, sample_knowledge
) -> None:
    repo = str(sample_knowledge.repository_id)
    hits = retriever.semantic_search(repo, "login endpoint")
    chunk = retriever.get_chunk(repo, hits[0].chunk_id)
    assert chunk is not None
    assert chunk.title == hits[0].title
    assert chunk.content
    assert chunk.relationships
    assert any(rel.kind == "defined_in" for rel in chunk.relationships)

    assert retriever.get_chunk(repo, "does-not-exist") is None


def test_retriever_without_index_returns_empty(
    index_settings, fake_embeddings, sample_knowledge
) -> None:
    retriever = KnowledgeRetriever(index_settings, embeddings=fake_embeddings)
    repo = str(sample_knowledge.repository_id)
    assert retriever.semantic_search(repo, "anything") == []
    assert retriever.hybrid_search(repo, "anything") == []
    items, total = retriever.list_chunks(repo)
    assert items == [] and total == 0
    assert retriever.stats(repo) is None
    assert retriever.get_chunk(repo, "x") is None
