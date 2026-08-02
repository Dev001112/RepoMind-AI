"""Context Compressor: dedupe, budget and section the ranked context so a
downstream agent gets the most information per token.

Pure heuristics:
  - dedupe on (type, title, summary-prefix): a chunk can arrive twice (seed
    leg + graph leg), AND genuinely-distinct chunks can carry the same
    knowledge (a route GET / registered in 17 test files -> 17 chunks, one
    fact); both collapse to a single row, keeping the highest-scoring member
  - estimate tokens = chars / 4, cut to `budget` while keeping type diversity
  - order output into stable sections (summary/architecture first, then
    files, apis, database, security, performance, dependencies, rest)
  - report the compression ratio (post/pre) and the collapsed count

No LLM: the summary field is stitched from the top summary/architecture
chunks verbatim, not generated.
"""

from dataclasses import dataclass, field

from app.models.schemas.retrieval import RerankedHit

DEFAULT_TOKEN_BUDGET = 6000
_SECTION_ORDER = {
    "summary": 0, "architecture": 1, "folder": 2, "file": 3,
    "api_endpoint": 4, "database": 5, "security": 6, "performance": 7,
    "dependency": 8, "deployment": 9, "cicd": 10, "docker": 11,
    "testing": 12, "documentation": 13,
}
_SECTION_RANK_MAX = max(_SECTION_ORDER.values()) + 1


# Length of the summary prefix used for near-duplicate detection. Two chunks
# with the same (type, title, summary-prefix) are the same *knowledge* even if
# they have distinct ids (e.g. a route GET / registered in 17 test files -- 17
# chunks, one fact). 120 chars is enough to distinguish genuinely different
# endpoints ("GET /login requires auth" vs "GET /add") without collapsing
# unrelated lookalikes.
_SUMMARY_PREFIX = 120


@dataclass
class CompressedContext:
    chunks: list[RerankedHit] = field(default_factory=list)
    summary: str | None = None
    ratio: float = 1.0
    dropped: int = 0
    collapsed: int = 0


def _estimate_tokens(content: str) -> int:
    return max(1, len(content) // 4)


def _section_rank(chunk_type: str) -> int:
    return _SECTION_ORDER.get(chunk_type, _SECTION_RANK_MAX)


def _content_key(hit: RerankedHit) -> tuple[str, str, str]:
    """Equivalence key: two chunks with the same key are the same knowledge
    (same type, same title, same summary lead-in) and should appear once."""
    summary = (hit.summary or "").strip().lower()[:_SUMMARY_PREFIX]
    return (hit.type, (hit.title or "").strip().lower(), summary)


class ContextCompressor:
    def __init__(self, budget: int = DEFAULT_TOKEN_BUDGET) -> None:
        self.budget = budget

    def compress(
        self,
        hits: list[RerankedHit],
        budget: int | None = None,
    ) -> CompressedContext:
        budget = budget or self.budget
        by_content: dict[tuple[str, str, str], RerankedHit] = {}
        collapsed = 0
        for hit in hits:
            # First dedup on chunk_id (a chunk can arrive via the seed leg and
            # the graph leg) -- keep the highest-scoring copy.
            key = _content_key(hit)
            existing = by_content.get(key)
            if existing is None:
                by_content[key] = hit
            elif hit.display_score > existing.display_score:
                by_content[key] = hit
                collapsed += 1
            else:
                # Same knowledge, lower score -- drop it.
                collapsed += 1

        ordered = sorted(
            by_content.values(),
            key=lambda h: (_section_rank(h.type), -h.display_score, h.title.lower()),
        )
        total_tokens = sum(_estimate_tokens(h.summary or h.title) for h in ordered)
        kept: list[RerankedHit] = []
        used = 0
        for hit in ordered:
            cost = _estimate_tokens(hit.summary or hit.title)
            if used + cost > budget and kept:
                break
            kept.append(hit)
            used += cost

        summary = _stitch_summary(kept)
        ratio = round(total_tokens / max(1, used), 2) if kept else 1.0
        return CompressedContext(
            chunks=kept,
            summary=summary,
            ratio=ratio,
            dropped=max(0, len(ordered) - len(kept)),
            collapsed=collapsed,
        )


def _stitch_summary(hits: list[RerankedHit]) -> str | None:
    """Verbatim lead-ins from the most relevant summary/architecture chunks,
    never generated text -- a retrieval stage must not fabricate."""
    candidates = [
        h for h in hits
        if h.type in {"summary", "architecture", "folder"} and h.summary.strip()
    ]
    if not candidates:
        return None
    top = candidates[:2]
    pieces = []
    for hit in top:
        lead = hit.summary.strip()
        pieces.append(f"[{hit.title}] {lead}")
    return " | ".join(pieces)[:1200]


def get_compressor(budget: int = DEFAULT_TOKEN_BUDGET) -> ContextCompressor:
    return ContextCompressor(budget)
