import { apiClient } from "@/services/apiClient";
import type {
  AnalysisEvent,
  AnalysisRun,
  ChatResponse,
  ChunkListResponse,
  DetectorResult,
  ExplainResponse,
  FileDetail,
  KnowledgeSearchResponse,
  KnowledgeStats,
  ProgressResponse,
  Repository,
  RepositoryCard,
  RepositoryKnowledge,
  RepositoryMetric,
  SearchResponse,
} from "@/types/repository";

export async function getRepositories(limit = 50): Promise<RepositoryCard[]> {
  const { data } = await apiClient.get<RepositoryCard[]>("/repositories", { params: { limit } });
  return data;
}

export async function submitRepository(sourceUrl: string): Promise<Repository> {
  const { data } = await apiClient.post<Repository>("/repositories", { sourceUrl });
  return data;
}

export async function uploadRepository(file: File): Promise<Repository> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await apiClient.post<Repository>("/repositories/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function getRepository(id: string): Promise<Repository> {
  const { data } = await apiClient.get<Repository>(`/repositories/${id}`);
  return data;
}

export async function getRepositoryKnowledge(id: string): Promise<RepositoryKnowledge> {
  const { data } = await apiClient.get<RepositoryKnowledge>(`/repositories/${id}/knowledge`);
  return data;
}

export async function getRepositoryProgress(id: string): Promise<ProgressResponse> {
  const { data } = await apiClient.get<ProgressResponse>(`/repositories/${id}/progress`);
  return data;
}

export async function getRepositoryMetrics(id: string): Promise<RepositoryMetric[]> {
  const { data } = await apiClient.get<RepositoryMetric[]>(`/repositories/${id}/metrics`);
  return data;
}

export async function getRepositoryAnalysisRuns(id: string): Promise<AnalysisRun[]> {
  const { data } = await apiClient.get<AnalysisRun[]>(`/repositories/${id}/analysis`);
  return data;
}

export async function getRepositoryEvents(id: string, limit = 100): Promise<AnalysisEvent[]> {
  const { data } = await apiClient.get<AnalysisEvent[]>(`/repositories/${id}/events`, {
    params: { limit },
  });
  return data;
}

export async function getRepositoryDetectors(id: string): Promise<DetectorResult[]> {
  const { data } = await apiClient.get<DetectorResult[]>(`/repositories/${id}/detectors`);
  return data;
}

export async function chatWithRepository(id: string, question: string): Promise<ChatResponse> {
  const { data } = await apiClient.post<ChatResponse>(`/repositories/${id}/chat`, { question });
  return data;
}

export async function reanalyzeRepository(id: string): Promise<Repository> {
  const { data } = await apiClient.post<Repository>(`/repositories/${id}/reanalyze`);
  return data;
}

export async function searchRepository(
  id: string,
  query: string,
  limit = 10,
): Promise<SearchResponse> {
  const { data } = await apiClient.post<SearchResponse>(`/repositories/${id}/search`, {
    query,
    limit,
  });
  return data;
}

export async function explainTarget(id: string, target: string): Promise<ExplainResponse> {
  const { data } = await apiClient.post<ExplainResponse>(`/repositories/${id}/explain`, {
    target,
  });
  return data;
}

export async function getFileDetail(id: string, filePath: string): Promise<FileDetail> {
  // filePath is interpolated as-is (not encodeURIComponent'd) -- the backend's
  // {file_path:path} route expects literal "/" separators, not "%2F".
  const { data } = await apiClient.get<FileDetail>(`/repositories/${id}/files/${filePath}`);
  return data;
}

export async function getKnowledgeStats(id: string): Promise<KnowledgeStats> {
  const { data } = await apiClient.get<KnowledgeStats>(`/repositories/${id}/knowledge/stats`);
  return data;
}

export async function getRepositoryChunks(
  id: string,
  params: { chunkType?: string; page?: number; pageSize?: number } = {},
): Promise<ChunkListResponse> {
  const { data } = await apiClient.get<ChunkListResponse>(`/repositories/${id}/chunks`, {
    params: { chunk_type: params.chunkType, page: params.page, page_size: params.pageSize },
  });
  return data;
}

export async function searchRepositoryKnowledge(
  id: string,
  query: string,
  mode: "semantic" | "hybrid" = "semantic",
  filters: { type?: string } = {},
): Promise<KnowledgeSearchResponse> {
  const { data } = await apiClient.post<KnowledgeSearchResponse>(
    `/repositories/${id}/search/${mode}`,
    { query, limit: 10, filters },
  );
  return data;
}
