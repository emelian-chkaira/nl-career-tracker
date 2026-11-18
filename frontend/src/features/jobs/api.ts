import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import type { Job, SearchParams, SearchResult } from "@/shared/api/types";

export const useJobSearch = (p: SearchParams) =>
  useQuery({ queryKey: ["jobs", p], queryFn: () => api.get<SearchResult>("/jobs", p as Record<string, unknown>), placeholderData: keepPreviousData });
export const useJob = (id: number | null) => useQuery({ queryKey: ["job", id], enabled: id != null, queryFn: () => api.get<Job>(`/jobs/${id}`) });
export const useSuggest = (q: string) =>
  useQuery({ queryKey: ["suggest", q], enabled: q.trim().length >= 2, queryFn: () => api.get<{ skills: string[]; companies: string[]; titles: string[] }>("/jobs/suggest", { q }), staleTime: 60_000 });

export function useSetStage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, stage, notes }: { id: number; stage?: string; notes?: string }) => api.put(`/me/jobs/${id}`, { stage, notes }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["jobs"] }); qc.invalidateQueries({ queryKey: ["job"] }); qc.invalidateQueries({ queryKey: ["pipeline"] }); },
  });
}
export const liveSearch = (q: string) => api.post<{ task_id: number }>("/jobs/live-search", {}, { q });
export const taskStatus = (id: number) => api.get<{ id: number; status: string; progress: Record<string, unknown> | null }>(`/tasks/${id}`);
