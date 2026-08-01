import { useMutation, useQuery } from "@tanstack/react-query";

import {
  chatWithRepository,
  explainTarget,
  getFileDetail,
  getKnowledgeStats,
  getRepositories,
  getRepository,
  getRepositoryAnalysisRuns,
  getRepositoryChunks,
  getRepositoryDetectors,
  getRepositoryEvents,
  getRepositoryKnowledge,
  getRepositoryMetrics,
  getRepositoryProgress,
  reanalyzeRepository,
  searchRepository,
  searchRepositoryKnowledge,
  submitRepository,
  uploadRepository,
} from "@/services/repositoryService";

export function useRepositories() {
  return useQuery({
    queryKey: ["repositories"],
    queryFn: () => getRepositories(),
    refetchInterval: 5000,
  });
}

export function useSubmitRepository() {
  return useMutation({
    mutationFn: submitRepository,
  });
}

export function useUploadRepository() {
  return useMutation({
    mutationFn: uploadRepository,
  });
}

export function useRepository(id: string | undefined) {
  return useQuery({
    queryKey: ["repository", id],
    queryFn: () => getRepository(id as string),
    enabled: Boolean(id),
    // Analysis is async (Phase 2 work) -- poll while the repo hasn't reached a final state.
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "ready" || status === "failed" ? false : 4000;
    },
  });
}

export function useRepositoryKnowledge(id: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["repository-knowledge", id],
    queryFn: () => getRepositoryKnowledge(id as string),
    enabled: Boolean(id) && enabled,
    retry: false, // a 501 (not implemented yet) is expected in Phase 1, not worth retrying
  });
}

export function useRepositoryProgress(id: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["repository-progress", id],
    queryFn: () => getRepositoryProgress(id as string),
    enabled: Boolean(id) && enabled,
    // Poll while the pipeline is still running; stop once done/failed.
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "ready" || status === "failed" ? false : 2000;
    },
  });
}

export function useRepositoryMetrics(id: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["repository-metrics", id],
    queryFn: () => getRepositoryMetrics(id as string),
    enabled: Boolean(id) && enabled,
  });
}

export function useRepositoryAnalysisRuns(id: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["repository-runs", id],
    queryFn: () => getRepositoryAnalysisRuns(id as string),
    enabled: Boolean(id) && enabled,
  });
}

export function useRepositoryEvents(id: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["repository-events", id],
    queryFn: () => getRepositoryEvents(id as string),
    enabled: Boolean(id) && enabled,
  });
}

export function useRepositoryDetectors(id: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["repository-detectors", id],
    queryFn: () => getRepositoryDetectors(id as string),
    enabled: Boolean(id) && enabled,
  });
}

export function useRepositoryChat(id: string | undefined) {
  return useMutation({
    mutationFn: (question: string) => chatWithRepository(id as string, question),
  });
}

export function useReanalyzeRepository(id: string | undefined) {
  return useMutation({
    mutationFn: () => reanalyzeRepository(id as string),
  });
}

export function useSearchRepository(id: string | undefined) {
  return useMutation({
    mutationFn: (query: string) => searchRepository(id as string, query),
  });
}

export function useExplainTarget(id: string | undefined) {
  return useMutation({
    mutationFn: (target: string) => explainTarget(id as string, target),
  });
}

export function useFileDetail(id: string | undefined, filePath: string | undefined) {
  return useQuery({
    queryKey: ["file-detail", id, filePath],
    queryFn: () => getFileDetail(id as string, filePath as string),
    enabled: Boolean(id) && Boolean(filePath),
  });
}

export function useKnowledgeStats(id: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["knowledge-stats", id],
    queryFn: () => getKnowledgeStats(id as string),
    enabled: Boolean(id) && enabled,
    retry: false, // a 404 (nothing indexed yet) is expected while analysis runs
  });
}

export function useRepositoryChunks(
  id: string | undefined,
  params: { chunkType?: string; page?: number; pageSize?: number },
) {
  return useQuery({
    queryKey: ["repository-chunks", id, params.chunkType, params.page],
    queryFn: () => getRepositoryChunks(id as string, params),
    enabled: Boolean(id),
  });
}

export function useKnowledgeSearch(id: string | undefined) {
  return useMutation({
    mutationFn: ({
      query,
      mode,
      filters,
    }: {
      query: string;
      mode: "semantic" | "hybrid";
      filters: { type?: string };
    }) => searchRepositoryKnowledge(id as string, query, mode, filters),
  });
}
