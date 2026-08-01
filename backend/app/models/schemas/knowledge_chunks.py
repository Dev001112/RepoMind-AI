"""The semantic Knowledge Chunk -- the unit of the Semantic Knowledge Index.

Repository Knowledge is a report; Knowledge Chunks are a searchable index.
Each chunk is a self-contained, embeddable unit of *meaning* derived from a
RepositoryKnowledge document: "this API endpoint requires auth", "this folder
holds service-layer code", "the database is PostgreSQL and the ORM is
SQLAlchemy". Chunks are versioned and checksummed so re-analysis only
re-embeds what actually changed, and carry relationships to other chunks so
later milestones can traverse the knowledge graph instead of flat text.

Stored payload (Qdrant) is built from these models by the embedding service.
"""

import uuid
from datetime import datetime

from app.models.schemas.base import CamelModel


class ChunkRelationship(CamelModel):
    """A directed edge to another chunk: kind is the verb, target is the other
    chunk's stable id. Both endpoints exist in the same index."""

    kind: str
    target_chunk_id: str
    target_title: str
    target_type: str


class ChunkMetadata(CamelModel):
    """Everything a filter/rerank step might need, kept flat in the vector
    payload so Qdrant can index and filter on it without extra lookups."""

    repository: str | None = None
    language: str | None = None
    framework: str | None = None
    directory: str | None = None
    file: str | None = None
    symbol: str | None = None
    type: str
    importance: float
    confidence: float
    checksum: str
    version: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class KnowledgeChunk(CamelModel):
    """One indexed unit of repository knowledge.

    `id` is deterministic: sha1(repository_id | type | title). Same content in
    a later run => same id + same checksum => embedding skipped. Content change
    => same id, new checksum, version bumped, re-embedded.
    """

    id: str
    repository_id: uuid.UUID
    type: str
    title: str
    content: str
    metadata: ChunkMetadata
    relationships: list[ChunkRelationship] = []
    priority: float = 1.0
    checksum: str
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Search API schemas
# ---------------------------------------------------------------------------


class ChunkFilters(CamelModel):
    """Metadata pre-filters applied before vector search. All optional; each
    present value becomes a Qdrant FieldCondition."""

    type: str | None = None
    language: str | None = None
    framework: str | None = None
    directory: str | None = None
    file: str | None = None


class SemanticSearchRequest(CamelModel):
    query: str
    limit: int = 10
    filters: ChunkFilters = ChunkFilters()


class SearchHit(CamelModel):
    """A single search result -- a *knowledge* hit, never raw source text."""

    chunk_id: str
    type: str
    title: str
    summary: str
    score: float
    file: str | None = None
    symbol: str | None = None
    language: str | None = None
    framework: str | None = None
    directory: str | None = None
    importance: float
    confidence: float
    version: int
    related_chunks: list[dict] = []


class SemanticSearchResponse(CamelModel):
    query: str
    results: list[SearchHit]


class ChunkSummary(CamelModel):
    """The index view of one chunk -- no content, no embedding, just the
    payload fields, so the explorer can page through everything a repository
    knows cheaply."""

    chunk_id: str
    type: str
    title: str
    language: str | None = None
    framework: str | None = None
    directory: str | None = None
    file: str | None = None
    importance: float
    confidence: float
    version: int
    updated_at: datetime | None = None


class ChunkListResponse(CamelModel):
    repository_id: uuid.UUID
    total: int
    page: int
    page_size: int
    items: list[ChunkSummary]


class KnowledgeStats(CamelModel):
    """The explorer header stats -- the '321 chunks / 18 categories' numbers."""

    repository_id: uuid.UUID
    total_chunks: int
    categories: list[dict]
    languages: list[str]
    frameworks: list[str]
    files: int
    files_indexed: int


class ChunkDetail(CamelModel):
    chunk_id: str
    type: str
    title: str
    content: str
    summary: str | None = None
    language: str | None = None
    framework: str | None = None
    directory: str | None = None
    file: str | None = None
    symbol: str | None = None
    importance: float
    confidence: float
    version: int
    relationships: list[ChunkRelationship] = []
    related_chunks: list[dict] = []

    def to_search_hit(self) -> "SearchHit":
        return SearchHit(
            chunk_id=self.chunk_id,
            type=self.type,
            title=self.title,
            summary=self.content[:300],
            score=0.0,
            file=self.file,
            symbol=self.symbol,
            language=self.language,
            framework=self.framework,
            directory=self.directory,
            importance=self.importance,
            confidence=self.confidence,
            version=self.version,
            related_chunks=self.related_chunks,
        )


class IndexStats(CamelModel):
    """Report from one index run: what was embedded, skipped, deleted."""

    total: int
    embedded: int
    skipped: int
    removed: int
    collection: str
    run_id: str
