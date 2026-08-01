/**
 * Mirrors the backend's Pydantic schemas (app/models/schemas/*.py), which emit
 * camelCase JSON via CamelModel. Keep in sync with those response models.
 */
export type RepositoryStatus =
  | "pending"
  | "cloning"
  | "scanning"
  | "knowledge_built"
  | "embedding"
  | "ready"
  | "failed";

export interface Repository {
  id: string;
  sourceUrl: string | null;
  uploadFilename: string | null;
  status: RepositoryStatus;
  localPath: string | null;
  lastError: string | null;
  lastErrorStage: string | null;
  lastAnalyzedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

/** Mirrors backend RepositoryCardRead -- dashboard card payload. */
export interface RepositoryCard {
  id: string;
  sourceUrl: string | null;
  uploadFilename: string | null;
  status: RepositoryStatus;
  lastAnalyzedAt: string | null;
  createdAt: string;
  knowledgeName: string | null;
  languages: string[];
  frameworks: string[];
  metrics: Record<string, number>;
}

export interface LanguageStat {
  name: string;
  fileCount: number;
}

export interface ApiEndpoint {
  method: string | null;
  path: string | null;
  file: string;
}

/** Mirrors backend/app/models/schemas/knowledge.py section-for-section. */
export interface RepositoryKnowledge {
  id: string | null;
  repositoryId: string;
  metadata: {
    name: string | null;
    description: string | null;
    repositoryType: string | null;
    license: string | null;
    mainEntryPoint: string | null;
    analyzedAt: string | null;
  };
  languages: { languages: string[]; stats: LanguageStat[] };
  frameworks: { frameworks: string[] };
  dependencies: {
    dependencies: Record<string, string>;
    packageManagers: string[];
    libraries: string[];
  };
  architecture: {
    summary: string | null;
    folderStructure: Record<string, unknown>;
    productionReadiness: string | null;
    difficultyLevel: string | null;
    useCases: string[];
    potentialApplications: string[];
  };
  files: { totalFiles: number; folderStructure: Record<string, unknown> };
  symbols: { totalSymbols: number };
  imports: { dependencyGraph: Record<string, string[]> };
  apis: { endpoints: ApiEndpoint[] };
  databases: { databases: string[]; orms: string[] };
  docker: { dockerSupport: boolean | null; dockerfilePath: string | null; composeServices: string[] };
  cuda: { gpuRequired: boolean | null; cudaRequired: boolean | null };
  cicd: { providers: string[]; workflowFiles: string[] };
  deployment: { platforms: string[] };
  testing: { frameworks: string[]; hasTests: boolean; testFileCount: number };
  documentation: {
    hasReadme: boolean;
    installationSteps: string[];
    hasContributing: boolean;
    hasLicenseFile: boolean;
  };
  performance: { notes: string[] };
  security: { findings: string[] };
  quality: { totalFiles: number; totalLines: number; todoCount: number };
  createdAt: string | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  answer: string;
  sources: string[];
}

export interface SearchResult {
  filePath: string;
  startLine: number;
  endLine: number;
  language: string;
  symbolName: string | null;
  snippet: string;
  score: number;
}

export interface SearchResponse {
  results: SearchResult[];
}

export interface ExplainResponse {
  target: string;
  explanation: string;
  sources: string[];
}

export interface FileSymbol {
  symbolName: string;
  startLine: number;
  endLine: number;
}

export interface FileDetail {
  path: string;
  content: string;
  language: string | null;
  symbols: FileSymbol[];
}

/** Mirrors backend/app/models/schemas/analysis.py. */
export interface AnalysisRun {
  id: string;
  repositoryId: string;
  status: "running" | "completed" | "failed" | "skipped";
  trigger: string;
  commitSha: string | null;
  startedAt: string;
  finishedAt: string | null;
  durationMs: number | null;
  error: string | null;
}

export interface AnalysisEvent {
  id: string;
  repositoryId: string;
  runId: string | null;
  eventName: string;
  stage: string | null;
  level: string;
  message: string | null;
  data: Record<string, unknown>;
  createdAt: string;
}

export interface DetectorResult {
  id: string;
  repositoryId: string;
  runId: string | null;
  detectorName: string;
  detectorVersion: string;
  confidence: number;
  startedAt: string | null;
  finishedAt: string | null;
  durationMs: number | null;
  warnings: string[];
  errors: string[];
  payload: Record<string, unknown>;
}

export interface RepositoryMetric {
  metricName: string;
  metricValue: number;
  unit: string | null;
}

export interface DetectorProgress {
  name: string;
  label: string;
  percent: number;
}

export interface StageProgress {
  name: string;
  label: string;
  percent: number;
  state: "done" | "active" | "queued" | "failed";
  detectors: DetectorProgress[];
}

export interface ProgressResponse {
  status: RepositoryStatus;
  overallPercent: number;
  stages: StageProgress[];
  message: string | null;
}

/** Mirrors backend/app/models/schemas/knowledge_chunks.py (Phase 3.2). */
export interface KnowledgeStats {
  repositoryId: string;
  totalChunks: number;
  categories: { type: string; count: number }[];
  languages: string[];
  frameworks: string[];
  files: number;
  filesIndexed: number;
}

export interface ChunkSummary {
  chunkId: string;
  type: string;
  title: string;
  language: string | null;
  framework: string | null;
  directory: string | null;
  file: string | null;
  importance: number;
  confidence: number;
  version: number;
  updatedAt: string | null;
}

export interface ChunkListResponse {
  repositoryId: string;
  total: number;
  page: number;
  pageSize: number;
  items: ChunkSummary[];
}

export interface KnowledgeSearchHit {
  chunkId: string;
  type: string;
  title: string;
  summary: string;
  score: number;
  file: string | null;
  symbol: string | null;
  language: string | null;
  framework: string | null;
  directory: string | null;
  importance: number;
  confidence: number;
  version: number;
  relatedChunks: {
    kind: string;
    chunkId: string;
    title: string;
    type: string;
  }[];
}

export interface KnowledgeSearchResponse {
  query: string;
  results: KnowledgeSearchHit[];
}
