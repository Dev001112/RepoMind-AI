import { apiClient } from "@/services/apiClient";
import type {
  ChatResponse,
  ExplainResponse,
  FileDetail,
  Repository,
  RepositoryKnowledge,
  SearchResponse,
} from "@/types/repository";

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
