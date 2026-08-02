"""Context Ranker: scores every candidate (seed hits + expanded neighbors)
into a single 0..100 display score and orders the context.

Score = 0.50 * similarity
      + 0.20 * importance (0..1, knowledge priorities)
      + 0.10 * confidence (0..1, enrichment confidence)
      + 0.10 * type fit (does the chunk type match the intent's target types)
      + 0.10 * hop discount (direct hits beat expanded neighbors)

All weights are module constants so the stage is trivially tunable and the
behavior is deterministic for tests.
"""

from app.models.schemas.retrieval import RerankedHit, RetrievalIntent

W_SIM = 0.50
W_IMPORTANCE = 0.20
W_CONFIDENCE = 0.10
W_TYPE = 0.10
W_HOP = 0.10


class ContextReranker:
    def __init__(self, target_types: list[str] | None = None) -> None:
        self.target_types = set(target_types or [])

    def rerank(
        self,
        hits: list[RerankedHit],
        intent: RetrievalIntent | None = None,
        target_types: list[str] | None = None,
    ) -> list[RerankedHit]:
        if target_types is not None:
            self.target_types = set(target_types)
        for hit in hits:
            similarity = _clamp01(hit.score)
            type_fit = 1.0 if hit.type in self.target_types else 0.35
            hop_discount = 1.0 if hit.hop == 0 else max(0.6, 1.0 - 0.35 * hit.hop)
            score = (
                W_SIM * similarity
                + W_IMPORTANCE * _clamp01(hit.importance)
                + W_CONFIDENCE * _clamp01(hit.confidence)
                + W_TYPE * type_fit
                + W_HOP * hop_discount
            )
            hit.display_score = round(min(100.0, max(0.0, score * 100.0)))
        return sorted(hits, key=lambda h: (-h.display_score, -h.score, h.title.lower()))


def _clamp01(value: float | None) -> float:
    if value is None:
        return 0.0
    return min(1.0, max(0.0, float(value)))


def get_reranker(target_types: list[str] | None = None) -> ContextReranker:
    return ContextReranker(target_types)
