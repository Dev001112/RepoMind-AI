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
  createdAt: string;
  updatedAt: string;
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
