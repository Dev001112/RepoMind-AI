/**
 * Phase 3.3 — Intelligent Retrieval types.
 *
 * Mirrors backend/app/models/schemas/retrieval.py. Backend emits camelCase
 * JSON via CamelModel; these interfaces match that wire format exactly.
 */

export type RetrievalIntent =
  | "architecture"
  | "explanation"
  | "setup"
  | "deployment"
  | "api"
  | "database"
  | "security"
  | "performance"
  | "dependencies"
  | "documentation"
  | "file_lookup"
  | "function_lookup"
  | "class_lookup"
  | "comparison"
  | "bug_investigation"
  | "feature_location";

export type SearchMode =
  | "auto"
  | "semantic"
  | "hybrid"
  | "exact"
  | "relationship"
  | "architecture"
  | "dependency"
  | "documentation";

export interface ChunkFilters {
  type?: string | null;
  language?: string | null;
  framework?: string | null;
  directory?: string | null;
  file?: string | null;
}

export interface RerankedHit {
  chunkId: string;
  type: string;
  title: string;
  summary: string;
  score: number;
  displayScore: number;
  hop: number;
  file: string | null;
  symbol: string | null;
  language: string | null;
  framework: string | null;
  directory: string | null;
  importance: number;
  confidence: number;
  version: number;
  relatedChunks: { kind: string; chunkId: string; title: string; type: string }[];
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  hop: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  kind: string;
  label: string;
}

export interface KnowledgeGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface Citation {
  chunkId: string;
  title: string;
  type: string;
  file: string | null;
}

export interface ExtractedMetadata {
  type: string | null;
  language: string | null;
  framework: string | null;
  directory: string | null;
  file: string | null;
  symbol: string | null;
  apiRoute: string | null;
}

export interface RetrievalMetrics {
  latencyMs: number;
  cacheHit: boolean;
  cacheKey: string | null;
  totalCandidates: number;
  returnedChunks: number;
  compressionRatio: number;
}

export interface RetrievalContext {
  query: string;
  intent: RetrievalIntent;
  rewrittenQuery: string;
  chunks: RerankedHit[];
  relationships: { kind: string; targetChunkId: string; targetTitle: string; targetType: string }[];
  summary: string | null;
  confidence: number;
  metadata: ExtractedMetadata;
  citations: Citation[];
  repositoryVersion: string | null;
  graph: KnowledgeGraph;
  metrics: RetrievalMetrics;
}

export interface RetrieveRequest {
  query: string;
  mode?: SearchMode;
  filters?: ChunkFilters | null;
  limit?: number;
  expansionDepth?: number;
  includeGraph?: boolean;
  tokenBudget?: number | null;
}

export interface SearchResponse {
  context: RetrievalContext;
}

export interface LookupResponse {
  query: string;
  results: RerankedHit[];
}

export interface SuggestionResponse {
  query: string;
  items: string[];
}

export interface QueryHistoryRecord {
  id: string;
  repositoryId: string;
  query: string;
  intent: RetrievalIntent;
  mode: SearchMode;
  latencyMs: number;
  chunkCount: number;
  cacheHit: boolean;
  qualityScore: number;
  createdAt: string;
}

export interface QueryHistoryResponse {
  total: number;
  items: QueryHistoryRecord[];
}

export interface RetrievalMetricsResponse {
  totalQueries: number;
  avgLatencyMs: number;
  cacheHitRate: number;
  topIntents: { intent: RetrievalIntent; count: number }[];
  recent24h: number;
}
