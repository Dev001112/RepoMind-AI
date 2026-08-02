"""Relationship Expansion: walk the knowledge graph stored in chunk payloads.

Every chunk carries `related_chunks` edges (kind/target_chunk_id/title/type).
Starting from the seed hits, this stage collects one-to-two-hop neighbors so a
context comes with its neighborhood -- e.g. an API endpoint result brings the
file chunk that implements it and the database chunk it touches.

Budget-bounded: at most MAX_TOTAL nodes, at most MAX_NEIGHBORS per node, and
never a second hop deeper than the plan allows. Deterministic ordering.
"""

from dataclasses import dataclass, field

from app.models.schemas.knowledge_chunks import ChunkRelationship
from app.models.schemas.retrieval import GraphEdge, GraphNode, RerankedHit

MAX_TOTAL = 32
MAX_NEIGHBORS = 6


@dataclass
class ExpansionResult:
    """Neighbors found, edges walked, and the mini graph for the UI."""

    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    expanded_hits: list[RerankedHit] = field(default_factory=list)
    relationships: list[ChunkRelationship] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.expanded_hits)


class RelationshipExpander:
    """Walks edges of seed hits via a `get_chunk` callback, so tests inject a
    dict-backed stub instead of Qdrant."""

    def __init__(self, get_chunk: callable) -> None:
        self._get_chunk = get_chunk

    def expand(
        self,
        seeds: list[RerankedHit],
        depth: int = 1,
    ) -> ExpansionResult:
        result = ExpansionResult()
        if depth < 1 or not seeds:
            return result

        seed_ids = {hit.chunk_id for hit in seeds}
        for hit in seeds:
            result.nodes.append(GraphNode(id=hit.chunk_id, label=hit.title, type=hit.type, hop=0))

        visited: set[str] = set(seed_ids)
        frontier = [hit.chunk_id for hit in seeds]
        for hop in range(1, min(depth, 2) + 1):
            if len(result.nodes) >= MAX_TOTAL:
                break
            next_frontier: list[str] = []
            for chunk_id in frontier:
                if len(result.nodes) >= MAX_TOTAL:
                    break
                detail = self._get_chunk(chunk_id)
                if detail is None:
                    continue
                seen_neighbors = 0
                for rel in detail.relationships:
                    if seen_neighbors >= MAX_NEIGHBORS:
                        break
                    target_id = rel.target_chunk_id
                    if target_id in visited or not target_id:
                        continue
                    visited.add(target_id)
                    seen_neighbors += 1
                    result.edges.append(
                        GraphEdge(
                            source=chunk_id,
                            target=target_id,
                            kind=rel.kind,
                            label=f"{rel.kind}: {rel.target_title}",
                        )
                    )
                    result.relationships.append(
                        ChunkRelationship(
                            kind=rel.kind,
                            target_chunk_id=target_id,
                            target_title=rel.target_title,
                            target_type=rel.target_type,
                        )
                    )
                    neighbor = self._get_chunk(target_id)
                    if neighbor is not None:
                        hit = neighbor.to_search_hit()
                        result.expanded_hits.append(
                            RerankedHit(
                                **hit.model_dump(),
                                display_score=0,
                                hop=hop,
                            )
                        )
                    result.nodes.append(
                        GraphNode(
                            id=target_id,
                            label=rel.target_title,
                            type=rel.target_type,
                            hop=hop,
                        )
                    )
                    next_frontier.append(target_id)
                frontier = next_frontier
        return result


def get_relationship_expander(get_chunk: callable) -> RelationshipExpander:
    return RelationshipExpander(get_chunk)
