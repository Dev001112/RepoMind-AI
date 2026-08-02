"""Context Builder: assembles the final RetrievalContext from the pipeline's
stage outputs -- the single contract a future agent (or the UI) consumes.

Also owns the quality signals: confidence is the weighted mean of the top
scores, repository_version comes from the top chunk's version, citations are
the kept chunks, and the graph is whatever the relationship stage found.
"""

from dataclasses import dataclass, field

from app.models.schemas.knowledge_chunks import ChunkRelationship
from app.models.schemas.retrieval import (
    Citation,
    ExtractedMetadata,
    KnowledgeGraph,
    RetrievalContext,
    RetrievalIntent,
    RetrievalMetrics,
    RerankedHit,
)

CONFIDENCE_FLOOR = 0.05


@dataclass
class StageOutputs:
    query: str
    intent: RetrievalIntent
    rewritten_query: str
    terms: list[str]
    metadata: ExtractedMetadata
    hits: list[RerankedHit]
    relationships: list[ChunkRelationship]
    graph: KnowledgeGraph
    summary: str | None
    metrics: RetrievalMetrics
    repository_version: str | None = None


class ContextBuilder:
    def build(self, stages: StageOutputs) -> RetrievalContext:
        hits = stages.hits
        top_scores = [h.display_score / 100.0 for h in hits[:3] if h.display_score > 0]
        confidence = sum(top_scores) / len(top_scores) if top_scores else CONFIDENCE_FLOOR

        citations = [
            Citation(
                chunk_id=h.chunk_id,
                title=h.title,
                type=h.type,
                file=h.file,
            )
            for h in hits[:5]
        ]

        version = stages.repository_version
        if version is None and hits:
            version = str(max(h.version for h in hits))

        metrics = stages.metrics
        metrics.returned_chunks = len(hits)

        return RetrievalContext(
            query=stages.query,
            intent=stages.intent,
            rewritten_query=stages.rewritten_query,
            chunks=hits,
            relationships=stages.relationships,
            summary=stages.summary,
            confidence=round(confidence, 4),
            metadata=stages.metadata,
            citations=citations,
            repository_version=version,
            graph=stages.graph,
            metrics=metrics,
        )


def get_context_builder() -> ContextBuilder:
    return ContextBuilder()
