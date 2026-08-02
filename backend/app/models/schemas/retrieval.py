"""The Intelligent Retrieval domain model -- the Phase 3.3 contract.

A retrieval run turns a user query into a RetrievalContext: the question, the
detected intent, the rewritten (expanded) query, the ranked knowledge chunks,
the relationships that connect them (the knowledge graph), a human summary,
a confidence score, extracted metadata, and citations -- everything a future
agent needs to answer the question, with zero LLM calls during retrieval.

The pipeline is: User Query -> Intent Analyzer -> Query Rewriter -> Metadata
Extractor -> Retrieval Planner -> Hybrid Search -> Relationship Expansion ->
Context Ranking -> Context Builder -> RetrievalContext. Each stage is an
independent service; nothing here talks to the LLM.
"""

import uuid
from datetime import datetime
from enum import Enum

from app.models.schemas.base import CamelModel
from app.models.schemas.knowledge_chunks import (
    ChunkFilters,
    ChunkRelationship,
    SearchHit,
)


class RetrievalIntent(str, Enum):
    """The 16 supported question intents. Every query is classified into one
    primary intent (plus scored alternatives), which drives the plan."""

    ARCHITECTURE = "architecture"
    EXPLANATION = "explanation"
    SETUP = "setup"
    DEPLOYMENT = "deployment"
    API = "api"
    DATABASE = "database"
    SECURITY = "security"
    PERFORMANCE = "performance"
    DEPENDENCIES = "dependencies"
    DOCUMENTATION = "documentation"
    FILE_LOOKUP = "file_lookup"
    FUNCTION_LOOKUP = "function_lookup"
    CLASS_LOOKUP = "class_lookup"
    COMPARISON = "comparison"
    BUG_INVESTIGATION = "bug_investigation"
    FEATURE_LOCATION = "feature_location"


class SearchMode(str, Enum):
    """Explicit retrieval strategies. AUTO lets the planner pick from the
    intent; the rest force a single strategy."""

    AUTO = "auto"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"
    EXACT = "exact"
    RELATIONSHIP = "relationship"
    ARCHITECTURE = "architecture"
    DEPENDENCY = "dependency"
    DOCUMENTATION = "documentation"


class IntentMatch(CamelModel):
    """One intent hypothesis with its confidence and the terms that fired."""

    intent: RetrievalIntent
    score: float
    matched_terms: list[str] = []


class QueryAnalysis(CamelModel):
    """Output of the Intent Analyzer + Query Rewriter stages."""

    query: str
    primary_intent: RetrievalIntent
    intents: list[IntentMatch] = []
    rewritten_query: str
    terms: list[str] = []


class ExtractedMetadata(CamelModel):
    """Output of the Metadata Extractor: concrete repository facts the user
    named in the query (a framework, a path, a symbol...), turned into the
    pre-filters the retriever applies before searching."""

    type: str | None = None
    language: str | None = None
    framework: str | None = None
    directory: str | None = None
    file: str | None = None
    symbol: str | None = None
    api_route: str | None = None


class RetrievalPlan(CamelModel):
    """Output of the Retrieval Planner: which legs run, on which filters,
    with which expansion budget -- fully deterministic per intent+mode."""

    mode: SearchMode
    legs: list[str] = []
    filters: ChunkFilters = ChunkFilters()
    target_types: list[str] = []
    expansion_depth: int = 1
    max_chunks: int = 10


class RerankedHit(SearchHit):
    """A SearchHit plus the Context Ranker's 0..100 display score and the
    hop distance from the seed hits (0 = direct match)."""

    display_score: int = 0
    hop: int = 0


class GraphNode(CamelModel):
    """One knowledge-graph node: a chunk. `hop` is its distance from the
    seed hits so the preview can fade deeper hops."""

    id: str
    label: str
    type: str
    hop: int


class GraphEdge(CamelModel):
    """One knowledge-graph edge, mirroring ChunkRelationship."""

    source: str
    target: str
    kind: str
    label: str


class KnowledgeGraph(CamelModel):
    """The relationship-expansion result as a mini graph the UI can render."""

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []


class Citation(CamelModel):
    """A chunk that supports the answer -- the "sources" of a context."""

    chunk_id: str
    title: str
    type: str
    file: str | None = None


class RetrievalMetrics(CamelModel):
    """Per-run observability: where the results came from and how fast."""

    latency_ms: float = 0.0
    cache_hit: bool = False
    cache_key: str | None = None
    total_candidates: int = 0
    returned_chunks: int = 0
    compression_ratio: float = 1.0


class RetrievalContext(CamelModel):
    """The Phase 3.3 contract: everything a downstream agent (or the UI)
    needs to answer the original query. Built by the Context Builder."""

    query: str
    intent: RetrievalIntent
    rewritten_query: str
    chunks: list[RerankedHit] = []
    relationships: list[ChunkRelationship] = []
    summary: str | None = None
    confidence: float = 0.0
    metadata: ExtractedMetadata = ExtractedMetadata()
    citations: list[Citation] = []
    repository_version: str | None = None
    graph: KnowledgeGraph = KnowledgeGraph()
    metrics: RetrievalMetrics = RetrievalMetrics()


# ---------------------------------------------------------------------------
# API schemas
# ---------------------------------------------------------------------------


class RetrieveRequest(CamelModel):
    """POST /repositories/{id}/retrieve -- the full pipeline, one shot."""

    query: str
    mode: SearchMode = SearchMode.AUTO
    filters: ChunkFilters | None = None
    limit: int = 10
    expansion_depth: int = 1
    include_graph: bool = True
    token_budget: int | None = None


class RetrieveResponse(CamelModel):
    """The RetrievalContext itself is the response."""

    context: RetrievalContext


class SearchResponse(CamelModel):
    """POST /repositories/{id}/search -- the search-first UI response: the
    analysis (badges), the ranked hits, the graph preview and the metrics."""

    context: RetrievalContext


class LookupRequest(CamelModel):
    """POST /repositories/{id}/lookup -- exact lookups (file / function /
    class / symbol) for cases where fuzzy search would be wrong."""

    query: str
    kind: str | None = None  # file | function | class | symbol | api | any
    limit: int = 10


class LookupResponse(CamelModel):
    query: str
    results: list[RerankedHit]


class SuggestionResponse(CamelModel):
    """Query suggestions: intent-driven templates + repository facts
    (languages, frameworks, files, endpoints) matched to the prefix."""

    query: str
    items: list[str] = []


class QueryHistoryRecord(CamelModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    query: str
    intent: RetrievalIntent
    mode: SearchMode
    latency_ms: float
    chunk_count: int
    cache_hit: bool
    quality_score: float
    created_at: datetime


class QueryHistoryResponse(CamelModel):
    total: int
    items: list[QueryHistoryRecord] = []


class RetrievalMetricsResponse(CamelModel):
    """Dashboard numbers for a repository's retrieval activity."""

    total_queries: int
    avg_latency_ms: float
    cache_hit_rate: float
    top_intents: list[dict] = []
    recent_24h: int = 0
