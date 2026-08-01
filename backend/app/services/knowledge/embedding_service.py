"""Batched, incremental embedding of KnowledgeChunks into the vector index.

The milestone rule is "embedding must never block analysis" -- this runs in
the EMBEDDING pipeline stage, after knowledge is already persisted, and is
checksum-driven: a re-analysis only re-embeds chunks whose content or
metadata actually changed (same id + same checksum = skip), bumps the version
of changed chunks, and drops points that no longer exist. Nothing here talks
to the LLM; it is pure embedding-provider + Qdrant work.

Payload shape (flat, filterable, and backwards-compatible):
  chunk_id, repository_id, run_id, type, title, content, page_content,
  language, framework, directory, file, symbol, importance, confidence,
  priority, checksum, version, updated_at, related_chunks,
  metadata.{repository_id, run_id, file_path, symbol_name, language}
The `metadata` sub-dict keeps Phase 2 consumers working (chat retriever
filters on metadata.repository_id; code-intelligence reads metadata.file_path).
`page_content` keeps langchain_qdrant Documents populated for the same reason.
"""

import logging
import uuid
from collections.abc import Sequence

from langchain_core.embeddings import Embeddings
from qdrant_client.models import PointStruct

from app.ai.vectorstore.qdrant_store import (
    ensure_chunks_collection,
    get_qdrant_client,
    scroll_repository_payloads,
)
from app.core.config import Settings
from app.models.schemas.knowledge_chunks import IndexStats, KnowledgeChunk

logger = logging.getLogger(__name__)

_BATCH_SIZE = 32
_SCROLL_LIMIT = 10_000


def _payload_for(chunk: KnowledgeChunk, run_id: str, version: int) -> dict:
    m = chunk.metadata
    return {
        "chunk_id": chunk.id,
        "repository_id": str(chunk.repository_id),
        "run_id": run_id,
        "type": chunk.type,
        "title": chunk.title,
        "content": chunk.content,
        "page_content": chunk.content,
        "language": m.language,
        "framework": m.framework,
        "directory": m.directory,
        "file": m.file,
        "symbol": m.symbol,
        "importance": m.importance,
        "confidence": m.confidence,
        "priority": chunk.priority,
        "checksum": chunk.checksum,
        "version": version,
        "updated_at": chunk.updated_at.isoformat() if chunk.updated_at else None,
        "related_chunks": [
            {
                "kind": rel.kind,
                "chunk_id": rel.target_chunk_id,
                "title": rel.target_title,
                "type": rel.target_type,
            }
            for rel in chunk.relationships
        ],
        "metadata": {
            "repository_id": str(chunk.repository_id),
            "run_id": run_id,
            "file_path": m.file or "",
            "symbol_name": m.symbol,
            "language": m.language,
        },
    }


def index_knowledge_chunks(
    settings: Settings,
    repository_id: uuid.UUID,
    chunks: Sequence[KnowledgeChunk],
    embeddings: Embeddings,
    run_id: str,
) -> IndexStats:
    """Bring the index in sync with `chunks`, embedding only what changed.

    Returns stats so the pipeline can emit a meaningful event (embedded N,
    skipped M, removed K). Delete-removed happens only after the new points
    are confirmed written, so a mid-run failure never leaves a repository
    with zero retrievable chunks when it previously had working ones.
    """
    client = get_qdrant_client()
    repo_id_str = str(repository_id)
    existing = scroll_repository_payloads(client, settings, repo_id_str, limit=_SCROLL_LIMIT)
    by_chunk_id = {p.payload.get("chunk_id"): p for p in existing if p.payload.get("chunk_id")}

    if not chunks:
        # Nothing to index -- clear whatever this repository had, so the index
        # never shows knowledge that no longer exists.
        if existing:
            client.delete(
                collection_name=settings.qdrant_collection_name,
                points_selector=[p.id for p in existing],
            )
        return IndexStats(
            total=0, embedded=0, skipped=0, removed=len(existing),
            collection=settings.qdrant_collection_name, run_id=run_id,
        )

    vector_size = len(embeddings.embed_query(chunks[0].content[:200]))
    ensure_chunks_collection(client, settings, vector_size)

    current_ids = {chunk.id for chunk in chunks}
    to_embed: list[KnowledgeChunk] = []
    skipped_ids: list[int] = []
    for chunk in chunks:
        previous = by_chunk_id.get(chunk.id)
        if previous is not None and previous.payload.get("checksum") == chunk.checksum:
            skipped_ids.append(previous.id)
        else:
            to_embed.append(chunk)

    # Batch-embed only the changed/new chunks.
    points: list[PointStruct] = []
    for start in range(0, len(to_embed), _BATCH_SIZE):
        batch = to_embed[start : start + _BATCH_SIZE]
        vectors = embeddings.embed_documents([c.content for c in batch])
        for chunk, vector in zip(batch, vectors):
            previous = by_chunk_id.get(chunk.id)
            version = previous.payload.get("version", 0) + 1 if previous is not None else 1
            points.append(
                PointStruct(
                    id=uuid.uuid4().hex,
                    vector=vector,
                    payload=_payload_for(chunk, run_id, version),
                )
            )
    if points:
        client.upsert(collection_name=settings.qdrant_collection_name, points=points)

    # Refresh the run tag on skipped points so the sweep above/below stays
    # unambiguous (nothing else reads run_id -- filters are on repository_id
    # and chunk metadata -- so this is a cheap top-level touch, not a rewrite).
    if skipped_ids:
        client.set_payload(
            collection_name=settings.qdrant_collection_name,
            payload={"run_id": run_id},
            points=skipped_ids,
        )

    # Sweep: anything still stored for this repository that isn't a current
    # chunk goes -- chunks removed from the report, legacy Phase 2 file-chunk
    # points (no chunk_id), AND superseded points from an earlier run that a
    # re-embedded chunk replaced (same chunk_id, stale run_id). Skipped points
    # are preserved explicitly: `existing` is a pre-write snapshot, so their
    # refreshed run_id isn't visible to the payload checks below.
    skipped_id_set = set(skipped_ids)
    stale_ids = [
        p.id
        for p in existing
        if p.id not in skipped_id_set
        and (
            p.payload.get("chunk_id") not in current_ids
            or p.payload.get("run_id") != run_id
        )
    ]
    if stale_ids:
        client.delete(collection_name=settings.qdrant_collection_name, points_selector=stale_ids)

    return IndexStats(
        total=len(chunks),
        embedded=len(to_embed),
        skipped=len(skipped_ids),
        removed=len(stale_ids),
        collection=settings.qdrant_collection_name,
        run_id=run_id,
    )
