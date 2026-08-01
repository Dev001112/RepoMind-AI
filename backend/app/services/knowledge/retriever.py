"""The Semantic Knowledge Index retriever: metadata filter -> vector search ->
(rerank extension point). Serves semantic, hybrid and context search over
KnowledgeChunks, plus cheap index reads (list / stats / single chunk) for the
Knowledge Explorer.

Never returns raw vectors or raw source text -- hits are *knowledge*:
title, type, score, summary, file/symbol context, and the related chunks
stored as edges at index time.

Hybrid search fuses two retrieval legs -- a pure dense query and a dense
query constrained to full-text keyword matches on `content` -- with
reciprocal rank fusion computed locally (the two qdrant versions without a
vector-less FilterQuery/fusion API are everywhere in the wild; the local
math is equivalent to qdrant's RRF fusion and trivially replaceable later).
Rerank (a cross-encoder pass over the fused set) is deliberately not wired
here yet: it's an extension point the milestone reserves, and fusing first
means reranking can later act on one merged result set.
"""

import logging
import re
import uuid
from collections import Counter

from langchain_core.embeddings import Embeddings
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchText,
    MatchValue,
)

from app.ai.embeddings.factory import get_embeddings
from app.ai.vectorstore.qdrant_store import get_qdrant_client
from app.core.config import Settings
from app.models.schemas.knowledge_chunks import (
    ChunkDetail,
    ChunkFilters,
    ChunkSummary,
    KnowledgeStats,
    SearchHit,
)

logger = logging.getLogger(__name__)

_KEYWORD_RE = re.compile(r"[a-z0-9_]{2,}")
_MAX_CONTEXT_NEIGHBORS = 6
_RRF_K = 60
_RRF_LEG_SIZE_MULTIPLIER = 4


class KnowledgeRetriever:
    """Stateless per-request retriever; constructs its own Qdrant client and
    (lazily) the embedding provider. Tests inject a fake Embeddings."""

    def __init__(self, settings: Settings, embeddings: Embeddings | None = None) -> None:
        self.settings = settings
        self.client = get_qdrant_client()
        self._embeddings = embeddings

    def _embeddings_instance(self) -> Embeddings:
        if self._embeddings is None:
            self._embeddings = get_embeddings(self.settings)
        return self._embeddings

    def _collection_exists(self) -> bool:
        try:
            self.client.get_collection(self.settings.qdrant_collection_name)
            return True
        except (UnexpectedResponse, ValueError):
            return False

    # -- search -------------------------------------------------------------

    def semantic_search(
        self,
        repository_id: str,
        query: str,
        filters: ChunkFilters | None = None,
        limit: int = 10,
    ) -> list[SearchHit]:
        if not self._collection_exists():
            return []
        vector = self._embeddings_instance().embed_query(query)
        try:
            points = self._query(vector, self._build_filter(repository_id, filters), limit)
        except (UnexpectedResponse, ValueError) as exc:
            logger.warning("semantic search failed for %s: %s", repository_id, exc)
            return []
        return [self._to_hit(point) for point in points]

    def hybrid_search(
        self,
        repository_id: str,
        query: str,
        filters: ChunkFilters | None = None,
        limit: int = 10,
    ) -> list[SearchHit]:
        """Dense leg + full-text-keyword-constrained leg, fused with local RRF.

        Each leg retrieves limit*4 points; a point's hybrid score is the sum
        of 1/(K + rank) over the legs it appears in, so keyword matches rank
        above pure semantic lookalikes without drowning dense relevance."""
        if not self._collection_exists():
            return []
        keywords = _keyword_tokens(query)
        base_filter = self._build_filter(repository_id, filters)
        if not keywords:
            # Nothing to fuse with -- pure vector search.
            return self.semantic_search(repository_id, query, filters, limit)

        vector = self._embeddings_instance().embed_query(query)
        keyword_filter = Filter(
            must=[
                *base_filter.must,
                FieldCondition(key="content", match=MatchText(text=" ".join(keywords))),
            ]
        )
        leg_limit = limit * _RRF_LEG_SIZE_MULTIPLIER
        try:
            dense = self._query(vector, base_filter, leg_limit)
            keyword = self._query(vector, keyword_filter, leg_limit)
        except (UnexpectedResponse, ValueError) as exc:
            logger.warning("hybrid search failed for %s (falling back to semantic): %s", repository_id, exc)
            return self.semantic_search(repository_id, query, filters, limit)

        rrf: dict[str, tuple[object, float]] = {}
        for rank, point in enumerate(dense):
            rrf[point.id] = (point, _RRF_K / (_RRF_K + rank))
        for rank, point in enumerate(keyword):
            if point.id in rrf:
                rrf[point.id] = (point, rrf[point.id][1] + _RRF_K / (_RRF_K + rank))
            else:
                rrf[point.id] = (point, _RRF_K / (_RRF_K + rank))

        merged = sorted(rrf.values(), key=lambda item: item[1], reverse=True)[:limit]
        return [self._to_hit(point) for point, _score in merged]

    def _query(self, vector, qdrant_filter: Filter, limit: int):
        return self.client.query_points(
            collection_name=self.settings.qdrant_collection_name,
            query=vector,
            query_filter=qdrant_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        ).points

    def context_search(
        self,
        repository_id: str,
        query: str,
        filters: ChunkFilters | None = None,
        limit: int = 5,
    ) -> list[SearchHit]:
        """Semantic search plus one hop along each hit's stored edges, so an
        answer can come with its neighborhood (e.g. an endpoint result carries
        the file chunk and the database chunk it touches)."""
        hits = self.semantic_search(repository_id, query, filters, limit)
        related: dict[str, SearchHit] = {}
        for hit in hits:
            for neighbor in hit.related_chunks[: _MAX_CONTEXT_NEIGHBORS]:
                neighbor_id = neighbor.get("chunk_id")
                if neighbor_id and neighbor_id not in related:
                    detail = self.get_chunk(repository_id, neighbor_id)
                    if detail is not None:
                        related[neighbor_id] = detail.to_search_hit()
        return [*hits, *related.values()]

    # -- index reads ----------------------------------------------------------

    def list_chunks(
        self,
        repository_id: str,
        *,
        chunk_type: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[ChunkSummary], int]:
        records = self._scroll_repository(repository_id)
        if chunk_type:
            records = [r for r in records if r.payload.get("type") == chunk_type]
        records.sort(key=lambda r: (r.payload.get("title") or "").lower())
        start = (page - 1) * page_size
        items = [
            self._to_summary(r.payload)
            for r in records[start : start + page_size]
        ]
        return items, len(records)

    def stats(self, repository_id: str) -> KnowledgeStats | None:
        records = self._scroll_repository(repository_id)
        if not records:
            return None
        payloads = [r.payload for r in records]
        types = Counter(p["type"] for p in payloads)
        languages = sorted({p["language"] for p in payloads if p.get("language")})
        frameworks = sorted({p["framework"] for p in payloads if p.get("framework")})
        files = sorted({p["file"] for p in payloads if p.get("file")})
        return KnowledgeStats(
            repository_id=uuid.UUID(repository_id),
            total_chunks=len(payloads),
            categories=[
                {"type": chunk_type, "count": count}
                for chunk_type, count in types.most_common()
            ],
            languages=languages,
            frameworks=frameworks,
            files=len(files),
            files_indexed=len(files),
        )

    def get_chunk(self, repository_id: str, chunk_id: str) -> ChunkDetail | None:
        try:
            points, _ = self.client.scroll(
                collection_name=self.settings.qdrant_collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="metadata.repository_id", match=MatchValue(value=repository_id)
                        ),
                        FieldCondition(key="chunk_id", match=MatchValue(value=chunk_id)),
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
        except (UnexpectedResponse, ValueError):
            return None
        if not points:
            return None
        return self._to_detail(points[0].payload)

    # -- internals -------------------------------------------------------------

    def _scroll_repository(self, repository_id: str) -> list:
        from app.ai.vectorstore.qdrant_store import scroll_repository_payloads

        if not self._collection_exists():
            return []
        return scroll_repository_payloads(
            self.client, self.settings, repository_id, limit=10_000
        )

    def _build_filter(self, repository_id: str, filters: ChunkFilters | None) -> Filter:
        must = [
            FieldCondition(key="metadata.repository_id", match=MatchValue(value=repository_id))
        ]
        if filters:
            for field in ("type", "language", "framework", "directory", "file"):
                value = getattr(filters, field)
                if value:
                    must.append(FieldCondition(key=field, match=MatchValue(value=value)))
        return Filter(must=must)

    @staticmethod
    def _to_hit(point) -> SearchHit:
        payload = point.payload
        return SearchHit(
            chunk_id=payload.get("chunk_id", ""),
            type=payload.get("type", ""),
            title=payload.get("title", ""),
            summary=(payload.get("content") or "")[:300],
            score=round(point.score, 4) if point.score is not None else 0.0,
            file=payload.get("file"),
            symbol=payload.get("symbol"),
            language=payload.get("language"),
            framework=payload.get("framework"),
            directory=payload.get("directory"),
            importance=payload.get("importance", 0.0),
            confidence=payload.get("confidence", 0.0),
            version=payload.get("version", 1),
            related_chunks=payload.get("related_chunks", []),
        )

    @staticmethod
    def _to_summary(payload: dict) -> ChunkSummary:
        return ChunkSummary(
            chunk_id=payload.get("chunk_id", ""),
            type=payload.get("type", ""),
            title=payload.get("title", ""),
            language=payload.get("language"),
            framework=payload.get("framework"),
            directory=payload.get("directory"),
            file=payload.get("file"),
            importance=payload.get("importance", 0.0),
            confidence=payload.get("confidence", 0.0),
            version=payload.get("version", 1),
            updated_at=payload.get("updated_at"),
        )

    @staticmethod
    def _to_detail(payload: dict) -> ChunkDetail:
        from app.models.schemas.knowledge_chunks import ChunkRelationship

        return ChunkDetail(
            chunk_id=payload.get("chunk_id", ""),
            type=payload.get("type", ""),
            title=payload.get("title", ""),
            content=payload.get("content", ""),
            language=payload.get("language"),
            framework=payload.get("framework"),
            directory=payload.get("directory"),
            file=payload.get("file"),
            symbol=payload.get("symbol"),
            importance=payload.get("importance", 0.0),
            confidence=payload.get("confidence", 0.0),
            version=payload.get("version", 1),
            relationships=[
                ChunkRelationship(
                    kind=rel.get("kind", ""),
                    target_chunk_id=rel.get("chunk_id", ""),
                    target_title=rel.get("title", ""),
                    target_type=rel.get("type", ""),
                )
                for rel in payload.get("related_chunks", [])
            ],
            related_chunks=payload.get("related_chunks", []),
        )


def _keyword_tokens(query: str) -> list[str]:
    """Deduped lowercase word tokens (length >= 2), e.g. 'login auth' for the
    full-text index. Qdrant's MatchText applies a word tokenizer anyway; this
    just keeps the query tidy."""
    return sorted(set(_KEYWORD_RE.findall(query.lower())))


def get_knowledge_retriever(settings: Settings) -> KnowledgeRetriever:
    return KnowledgeRetriever(settings)
