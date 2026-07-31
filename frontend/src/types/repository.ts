/**
 * Mirrors the backend's Pydantic schemas (app/models/schemas/*.py), which emit
 * camelCase JSON via CamelModel. Keep in sync with those response models.
 */
export type RepositoryStatus = "pending" | "cloning" | "analyzing" | "ready" | "failed";

export interface Repository {
  id: string;
  sourceUrl: string | null;
  uploadFilename: string | null;
  status: RepositoryStatus;
  localPath: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface RepositoryKnowledge {
  id: string | null;
  repositoryId: string;
  name: string | null;
  description: string | null;
  repositoryType: string | null;
  languages: string[];
  frameworks: string[];
  libraries: string[];
  dependencies: Record<string, string>;
  gpuRequired: boolean | null;
  cudaRequired: boolean | null;
  dockerSupport: boolean | null;
  installationSteps: string[];
  packageManagers: string[];
  productionReadiness: string | null;
  difficultyLevel: string | null;
  architectureSummary: string | null;
  mainEntryPoint: string | null;
  useCases: string[];
  potentialApplications: string[];
  license: string | null;
  securityFindings: string[];
  performanceNotes: string[];
  dependencyGraph: Record<string, string[]>;
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
