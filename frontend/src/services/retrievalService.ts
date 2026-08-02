import { apiClient } from "@/services/apiClient";
import type {
  LookupResponse,
  QueryHistoryResponse,
  RetrieveRequest,
  RetrievalContext,
  SearchMode,
  SearchResponse,
  SuggestionResponse,
  RetrievalMetricsResponse,
} from "@/types/retrieval";

/** Full intelligent-retrieval pipeline -- POST /retrieve -> RetrievalContext. */
export async function retrieveRepository(
  id: string,
  request: RetrieveRequest,
): Promise<RetrievalContext> {
  const { data } = await apiClient.post<{ context: RetrievalContext }>(
    `/repositories/${id}/retrieve`,
    request,
  );
  return data.context;
}

/** Search-first UX: the same pipeline, returning the UI-shaped context. */
export async function searchRepositoryIntelligent(
  id: string,
  request: RetrieveRequest,
): Promise<SearchResponse> {
  const { data } = await apiClient.post<SearchResponse>(
    `/repositories/${id}/search`,
    request,
  );
  return data;
}

/** Exact lookups -- file names, function names, class names, symbols. */
export async function lookupRepository(
  id: string,
  query: string,
  kind?: string,
  limit = 10,
): Promise<LookupResponse> {
  const { data } = await apiClient.post<LookupResponse>(`/repositories/${id}/lookup`, {
    query,
    kind: kind ?? undefined,
    limit,
  });
  return data;
}

/** Query suggestions for the input box, scoped to this repository. */
export async function getSuggestions(id: string, prefix = ""): Promise<SuggestionResponse> {
  const { data } = await apiClient.get<SuggestionResponse>(`/repositories/${id}/suggestions`, {
    params: { q: prefix },
  });
  return data;
}

export async function getQueryHistory(id: string, limit = 20): Promise<QueryHistoryResponse> {
  const { data } = await apiClient.get<QueryHistoryResponse>(`/repositories/${id}/history`, {
    params: { limit },
  });
  return data;
}

export async function getRetrievalMetrics(id: string): Promise<RetrievalMetricsResponse> {
  const { data } = await apiClient.get<RetrievalMetricsResponse>(
    `/repositories/${id}/retrieval/metrics`,
  );
  return data;
}

export type { SearchMode };
