"""IntelligentRetriever -- the Phase 3.3 orchestrator.

Runs the deterministic pipeline end to end:
  analyze (intent) -> rewrite -> extract metadata -> plan -> cache check ->
  search legs -> relationship expansion -> rerank -> compress -> build context

The engine is pure: it takes a KnowledgeRetriever and the stage services,
measures its own latency, and hands the caller (the API layer) everything it
needs to persist history. A per-repository RepoProfile is built lazily from
index stats + a payload scan and cached briefly, so metadata extraction can
match facts that actually exist in the index.
"""

import logging
import time
import uuid

from app.models.schemas.knowledge_chunks import ChunkFilters
from app.models.schemas.retrieval import (
    ExtractedMetadata,
    LookupResponse,
    QueryAnalysis,
    RerankedHit,
    RetrievalContext,
    RetrievalMetrics,
    RetrieveRequest,
    SearchMode,
    SuggestionResponse,
)
from app.services.retrieval.builder import ContextBuilder, StageOutputs, get_context_builder
from app.services.retrieval.cache import RetrievalCache, get_retrieval_cache
from app.services.retrieval.compressor import ContextCompressor, get_compressor
from app.services.retrieval.filters import FilterBuilder, get_filter_builder
from app.services.retrieval.intent import IntentAnalyzer, get_intent_analyzer
from app.services.retrieval.metadata import (
    MetadataExtractor,
    RepoProfile,
    get_metadata_extractor,
)
from app.services.retrieval.planner import RetrievalPlanner, get_planner
from app.services.retrieval.query_rewriter import QueryRewriter, get_query_rewriter
from app.services.retrieval.relationship import (
    RelationshipExpander,
    get_relationship_expander,
)
from app.services.retrieval.reranker import ContextReranker, get_reranker

logger = logging.getLogger(__name__)

_PROFILE_TTL_SECONDS = 300
_LEG_LIMIT_MULTIPLIER = 4
_MAX_EXACT = 12


class IntelligentRetriever:
    """Stateless per-request orchestrator over the stage services. The API
    layer owns the DB session; the engine stays transport-agnostic."""

    def __init__(
        self,
        knowledge_retriever,
        analyzer: IntentAnalyzer | None = None,
        rewriter: QueryRewriter | None = None,
        extractor: MetadataExtractor | None = None,
        planner: RetrievalPlanner | None = None,
        filter_builder: FilterBuilder | None = None,
        reranker: ContextReranker | None = None,
        compressor: ContextCompressor | None = None,
        builder: ContextBuilder | None = None,
        cache: RetrievalCache | None = None,
    ) -> None:
        self.knowledge = knowledge_retriever
        self.analyzer = analyzer or get_intent_analyzer()
        self.rewriter = rewriter or get_query_rewriter()
        self.extractor = extractor or get_metadata_extractor()
        self.planner = planner or get_planner()
        self.filter_builder = filter_builder or get_filter_builder()
        self.reranker = reranker or get_reranker()
        self.compressor = compressor or get_compressor()
        self.builder = builder or get_context_builder()
        self.cache = cache or get_retrieval_cache()
        self._profiles: dict[str, tuple[float, RepoProfile]] = {}

    # -- profile --------------------------------------------------------------

    def repo_profile(self, repository_id: str, force: bool = False) -> RepoProfile:
        now = time.monotonic()
        cached = self._profiles.get(repository_id)
        if not force and cached and now - cached[0] < _PROFILE_TTL_SECONDS:
            return cached[1]
        profile = self._build_profile(repository_id)
        self._profiles[repository_id] = (now, profile)
        return profile

    def _build_profile(self, repository_id: str) -> RepoProfile:
        profile = RepoProfile(repository_id=repository_id)
        try:
            stats = self.knowledge.stats(repository_id)
            if stats:
                profile.languages = set(stats.languages)
                profile.frameworks = set(stats.frameworks)
        except Exception as exc:  # index unreachable -> empty profile
            logger.warning("profile build for %s failed: %s", repository_id, exc)
        return profile

    # -- pipeline --------------------------------------------------------------

    def retrieve(
        self,
        repository_id: str,
        request: RetrieveRequest,
        *,
        skip_cache: bool = False,
    ) -> RetrievalContext:
        start = time.monotonic()
        query = request.query.strip()
        if not query:
            raise ValueError("query must not be empty")

        analysis = self.analyzer.analyze(query)
        rewritten, terms = self.rewriter.rewrite(query, analysis.terms)
        analysis.rewritten_query = rewritten
        analysis.terms = terms

        profile = self.repo_profile(repository_id)
        extractor = get_metadata_extractor(profile)
        metadata = extractor.extract(query)

        plan = self.planner.plan(
            intent=analysis.primary_intent,
            metadata=metadata,
            mode=request.mode,
            max_chunks=request.limit,
            expansion_depth=request.expansion_depth,
        )
        filters = self.filter_builder.build(metadata, request.filters)

        cache_key = self.cache.make_key(
            repository_id, query, request.mode, request.filters,
            request.limit, request.expansion_depth, request.token_budget,
        )
        if not skip_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                cached.metrics.cache_hit = True
                cached.metrics.cache_key = cache_key
                cached.metrics.latency_ms = round((time.monotonic() - start) * 1000, 2)
                return cached

        candidates = self._search_legs(repository_id, rewritten, filters, plan, raw_query=query)
        expander = get_relationship_expander(
            lambda chunk_id: self.knowledge.get_chunk(repository_id, chunk_id)
        )
        expanded = expander.expand(candidates, depth=plan.expansion_depth)
        from app.models.schemas.retrieval import KnowledgeGraph

        graph = KnowledgeGraph(nodes=expanded.nodes, edges=expanded.edges)
        merged = [*candidates, *expanded.expanded_hits]
        reranked = self.reranker.rerank(merged, target_types=plan.target_types)

        compressed = self.compressor.compress(reranked, budget=request.token_budget)
        metrics = RetrievalMetrics(
            total_candidates=len(reranked),
            returned_chunks=len(compressed.chunks),
            compression_ratio=compressed.ratio,
            cache_key=cache_key,
        )
        context = self.builder.build(
            StageOutputs(
                query=query,
                intent=analysis.primary_intent,
                rewritten_query=rewritten,
                terms=terms,
                metadata=metadata,
                hits=compressed.chunks,
                relationships=expanded.relationships,
                graph=graph,
                summary=compressed.summary,
                metrics=metrics,
            )
        )
        context.metrics.latency_ms = round((time.monotonic() - start) * 1000, 2)
        self.cache.set(cache_key, context)
        return context

    def _search_legs(
        self,
        repository_id: str,
        rewritten: str,
        filters: ChunkFilters,
        plan,
        raw_query: str = "",
    ) -> list[RerankedHit]:
        results: list[RerankedHit] = []
        leg_limit = plan.max_chunks * _LEG_LIMIT_MULTIPLIER

        if "exact" in plan.legs:
            # The exact leg matches on the *original* query -- the rewritten
            # query carries expansion terms that would never match a name.
            exact = self.knowledge.exact_lookup(
                repository_id, raw_query or rewritten,
                kind=_exact_kind(plan.mode),
                limit=_MAX_EXACT,
            )
            for hit in exact:
                results.append(RerankedHit(**hit.model_dump(), display_score=0, hop=0))

        if "semantic" in plan.legs or "hybrid" in plan.legs:
            if plan.mode == SearchMode.SEMANTIC or "semantic" in plan.legs:
                search_hits = self.knowledge.semantic_search(
                    repository_id, rewritten, filters=filters, limit=leg_limit
                )
            else:
                # The keyword leg tokenizes the *original* query: the rewriter's
                # synonyms ("authorization token jwt login") match the index's
                # vocabulary for embeddings but also fire on common import
                # statements, flooding the keyword leg with files that merely
                # `import flask`. The vector leg still embeds the richer rewrite.
                search_hits = self.knowledge.hybrid_search(
                    repository_id, rewritten,
                    filters=filters, limit=leg_limit,
                    keyword_query=raw_query or rewritten,
                )
            for hit in search_hits:
                results.append(RerankedHit(**hit.model_dump(), display_score=0, hop=0))

        return results

    # -- exact lookups ---------------------------------------------------------

    def lookup(self, repository_id: str, query: str, kind: str | None = None, limit: int = 10) -> LookupResponse:
        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        hits = self.knowledge.exact_lookup(repository_id, query, kind=kind, limit=limit)
        reranked = [
            RerankedHit(**hit.model_dump(), display_score=90, hop=0)
            for hit in hits
        ]
        return LookupResponse(query=query, results=reranked)

    # -- suggestions -----------------------------------------------------------

    def suggest(self, repository_id: str, prefix: str, limit: int = 10) -> SuggestionResponse:
        prefix = prefix.strip().lower()
        profile = self.repo_profile(repository_id)
        facts: list[str] = []
        if profile.languages:
            facts.append(f"how is {sorted(profile.languages)[0]} used in the project?")
        for framework in sorted(profile.frameworks)[:2]:
            facts.append(f"how is {framework} configured?")
        facts.append("what is the overall architecture?")
        facts.append("how does authentication work?")
        facts.append("what database is used?")
        facts.append("how do I run the project locally?")
        facts.append("how is the project deployed?")
        facts.append("are there security concerns?")

        if prefix:
            items = [f for f in facts if prefix in f.lower()][:limit]
        else:
            items = facts[:limit]
        return SuggestionResponse(query=prefix, items=items)


def get_intelligent_retriever(knowledge_retriever) -> IntelligentRetriever:
    return IntelligentRetriever(knowledge_retriever)


def _exact_kind(mode: SearchMode) -> str | None:
    if mode == SearchMode.ARCHITECTURE:
        return "folder"
    if mode == SearchMode.DEPENDENCY:
        return "dependency"
    if mode == SearchMode.DOCUMENTATION:
        return "documentation"
    return None
