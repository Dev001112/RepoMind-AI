import { useMutation, useQuery } from "@tanstack/react-query";

import {
  chatWithRepository,
  explainTarget,
  getFileDetail,
  getRepository,
  getRepositoryKnowledge,
  reanalyzeRepository,
  searchRepository,
  submitRepository,
  uploadRepository,
} from "@/services/repositoryService";

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
