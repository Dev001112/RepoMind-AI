"""Embedding-service tests: batched upsert, checksum-based incremental
indexing, version bumps, and stale-point sweeping -- against a throwaway
Qdrant collection and deterministic fake embeddings."""

import uuid

from app.services.knowledge.chunk_builder import build_knowledge_chunks
from app.services.knowledge.embedding_service import index_knowledge_chunks


def _index(sample_knowledge, index_settings, fake_embeddings, run_id):
    chunks = build_knowledge_chunks(sample_knowledge.repository_id, sample_knowledge)
    return chunks, index_knowledge_chunks(
        index_settings,
        sample_knowledge.repository_id,
        chunks,
        fake_embeddings,
        run_id=run_id,
    )


def test_first_index_embeds_everything(sample_knowledge, index_settings, fake_embeddings) -> None:
    chunks, stats = _index(sample_knowledge, index_settings, fake_embeddings, run_id="run-1")
    assert stats.total == len(chunks)
    assert stats.embedded == len(chunks)
    assert stats.skipped == 0
    assert stats.removed == 0
    assert stats.run_id == "run-1"


def test_reindex_skips_unchanged_and_bumps_versions(
    sample_knowledge, index_settings, fake_embeddings
) -> None:
    chunks, _ = _index(sample_knowledge, index_settings, fake_embeddings, run_id="run-1")
    _, second = _index(sample_knowledge, index_settings, fake_embeddings, run_id="run-2")

    assert second.embedded == 0
    assert second.skipped == len(chunks)
    assert second.removed == 0

    # One section changes -> exactly the chunks mentioning it get re-embedded,
    # and the superseded points for those chunks get swept.
    sample_knowledge.dependencies.dependencies["bcrypt"] = "5.0.0"
    _, third = _index(sample_knowledge, index_settings, fake_embeddings, run_id="run-3")
    assert third.embedded == 1
    assert third.skipped == len(chunks) - 1
    assert third.removed == 1


def test_removed_chunks_are_swept(sample_knowledge, index_settings, fake_embeddings) -> None:
    chunks, _ = _index(sample_knowledge, index_settings, fake_embeddings, run_id="run-1")
    # Delete every endpoint chunk from the report -> those points must vanish
    # from the index (everything else stays).
    sample_knowledge.apis.endpoints = []
    new_chunks = build_knowledge_chunks(sample_knowledge.repository_id, sample_knowledge)
    stats = index_knowledge_chunks(
        index_settings, sample_knowledge.repository_id, new_chunks, fake_embeddings, run_id="run-2"
    )
    endpoint_ids = {c.id for c in chunks if c.type == "api_endpoint"}
    # Removed = the endpoint chunks themselves + the old points superseded by
    # the two re-embedded file chunks (auth.py, routes.py changed content).
    assert stats.removed == len(endpoint_ids) + 2

    from app.services.knowledge.retriever import KnowledgeRetriever

    retriever = KnowledgeRetriever(index_settings, embeddings=fake_embeddings)
    remaining, total = retriever.list_chunks(str(sample_knowledge.repository_id))
    assert total == len(new_chunks)
    assert all(item.chunk_id not in endpoint_ids for item in remaining)


def test_empty_input_clears_the_index(sample_knowledge, index_settings, fake_embeddings) -> None:
    _index(sample_knowledge, index_settings, fake_embeddings, run_id="run-1")
    stats = index_knowledge_chunks(
        index_settings,
        sample_knowledge.repository_id,
        [],
        fake_embeddings,
        run_id="run-2",
    )
    assert stats.removed > 0

    from app.services.knowledge.retriever import KnowledgeRetriever

    _, total = KnowledgeRetriever(index_settings, embeddings=fake_embeddings).list_chunks(
        str(sample_knowledge.repository_id)
    )
    assert total == 0


def test_repositories_are_isolated(sample_knowledge, index_settings, fake_embeddings) -> None:
    repo_b = sample_knowledge.model_copy(deep=True)
    repo_b.repository_id = uuid.uuid4()
    chunks_b = build_knowledge_chunks(repo_b.repository_id, repo_b)
    _index(sample_knowledge, index_settings, fake_embeddings, run_id="run-1")
    index_knowledge_chunks(
        index_settings, repo_b.repository_id, chunks_b, fake_embeddings, run_id="run-2"
    )

    from app.services.knowledge.retriever import KnowledgeRetriever

    retriever = KnowledgeRetriever(index_settings, embeddings=fake_embeddings)
    _, total_a = retriever.list_chunks(str(sample_knowledge.repository_id))
    _, total_b = retriever.list_chunks(str(repo_b.repository_id))
    assert total_a > 0 and total_b > 0
