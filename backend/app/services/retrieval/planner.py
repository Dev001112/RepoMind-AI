"""Retrieval Planner: turns (intent, extracted metadata, requested mode) into
a concrete RetrievalPlan -- which search legs run, on which pre-filters, with
which relationship-expansion budget and target chunk types.

Fully deterministic per (intent, mode, metadata). The plan is what keeps the
retrieval explainable: the /explain endpoint can dump it verbatim.

Intent -> strategy mapping (AUTO mode):
  API / DATABASE / SECURITY / DEPENDENCIES   -> hybrid, type-restricted
  ARCHITECTURE / DOCUMENTATION               -> semantic, type-restricted
  FILE/ FUNCTION/ CLASS lookup               -> exact + hybrid (symbol leg)
  COMPARISON / EXPLANATION / BUG / FEATURE   -> hybrid + relationship expansion
  SETUP / DEPLOYMENT / PERFORMANCE           -> hybrid, broad
"""

from app.models.schemas.knowledge_chunks import ChunkFilters
from app.models.schemas.retrieval import (
    ExtractedMetadata,
    RetrievalIntent,
    RetrievalPlan,
    SearchMode,
)

_INTENT_DEFAULT_TYPES: dict[RetrievalIntent, list[str]] = {
    RetrievalIntent.API: ["api_endpoint", "file"],
    RetrievalIntent.DATABASE: ["database", "file", "architecture"],
    RetrievalIntent.SECURITY: ["security", "api_endpoint", "file"],
    RetrievalIntent.DEPENDENCIES: ["dependency", "file", "documentation"],
    RetrievalIntent.DEPLOYMENT: ["deployment", "cicd", "docker", "file", "documentation"],
    RetrievalIntent.SETUP: ["documentation", "file", "deployment"],
    RetrievalIntent.PERFORMANCE: ["performance", "file", "architecture"],
    RetrievalIntent.ARCHITECTURE: ["architecture", "folder", "summary", "file"],
    RetrievalIntent.DOCUMENTATION: ["documentation", "file", "architecture"],
    RetrievalIntent.FILE_LOOKUP: ["file", "folder"],
    RetrievalIntent.FUNCTION_LOOKUP: ["function", "file", "api_endpoint"],
    RetrievalIntent.CLASS_LOOKUP: ["class", "file"],
    RetrievalIntent.EXPLANATION: ["file", "api_endpoint", "database", "architecture"],
    RetrievalIntent.COMPARISON: ["file", "api_endpoint", "database", "architecture"],
    RetrievalIntent.BUG_INVESTIGATION: ["file", "api_endpoint", "database", "security", "performance"],
    RetrievalIntent.FEATURE_LOCATION: ["file", "architecture", "api_endpoint", "database"],
}

_MODE_TYPES: dict[SearchMode, list[str]] = {
    SearchMode.ARCHITECTURE: ["architecture", "folder", "summary", "file"],
    SearchMode.DEPENDENCY: ["dependency", "file", "documentation"],
    SearchMode.DOCUMENTATION: ["documentation", "file", "architecture"],
}

_EXPLORATORY_INTENTS = {
    RetrievalIntent.COMPARISON,
    RetrievalIntent.EXPLANATION,
    RetrievalIntent.BUG_INVESTIGATION,
    RetrievalIntent.FEATURE_LOCATION,
}

_MODE_LEGS: dict[SearchMode, list[str]] = {
    SearchMode.SEMANTIC: ["semantic"],
    SearchMode.HYBRID: ["hybrid"],
    SearchMode.EXACT: ["exact", "hybrid"],
    SearchMode.RELATIONSHIP: ["semantic", "relationship"],
    SearchMode.ARCHITECTURE: ["semantic", "relationship"],
    SearchMode.DEPENDENCY: ["hybrid"],
    SearchMode.DOCUMENTATION: ["semantic"],
    SearchMode.AUTO: ["hybrid"],
}


class RetrievalPlanner:
    def __init__(self) -> None:
        self._types = {k: v for k, v in _INTENT_DEFAULT_TYPES.items()}
        self._mode_types = {k: v for k, v in _MODE_TYPES.items()}
        self._exploratory = set(_EXPLORATORY_INTENTS)
        self._legs = {k: list(v) for k, v in _MODE_LEGS.items()}

    def plan(
        self,
        intent: RetrievalIntent,
        metadata: ExtractedMetadata,
        mode: SearchMode = SearchMode.AUTO,
        max_chunks: int = 10,
        expansion_depth: int = 1,
    ) -> RetrievalPlan:
        # The metadata the extractor found (and that actually exists in the
        # index) narrows the search first; intent supplies the rest.
        filters = ChunkFilters(
            type=metadata.type,
            language=metadata.language,
            framework=metadata.framework,
            directory=metadata.directory,
            file=metadata.file,
        )

        if mode == SearchMode.AUTO:
            if intent in self._exploratory:
                legs = ["hybrid", "relationship"]
                depth = max(expansion_depth, 1)
                types = self._types[intent]
            elif intent in {RetrievalIntent.FILE_LOOKUP, RetrievalIntent.FUNCTION_LOOKUP, RetrievalIntent.CLASS_LOOKUP}:
                legs = ["exact", "hybrid"]
                depth = expansion_depth
                types = self._types[intent]
            else:
                legs = ["hybrid"]
                depth = expansion_depth
                types = self._types.get(intent, ["file", "api_endpoint"])
        else:
            legs = self._legs[mode]
            depth = expansion_depth if "relationship" in legs else 0
            types = self._mode_types.get(mode) or self._types.get(intent, ["file"])

        return RetrievalPlan(
            mode=mode if mode != SearchMode.AUTO else SearchMode.HYBRID,
            legs=legs,
            filters=filters,
            target_types=types,
            expansion_depth=depth,
            max_chunks=max_chunks,
        )


def get_planner() -> RetrievalPlanner:
    return RetrievalPlanner()
