import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import type { Notification, SavedSearch, SearchParams } from "@/shared/api/types";

export const useSavedSearches = () => useQuery({ queryKey: ["searches"], queryFn: () => api.get<SavedSearch[]>("/me/searches") });
export const useNotifications = (enabled = true) =>
  useQuery({ queryKey: ["notifications"], enabled, refetchInterval: 60_000, queryFn: () => api.get<{ unread: number; items: Notification[] }>("/me/notifications") });

export function useSearchMutations() {
  const qc = useQueryClient(); const done = () => qc.invalidateQueries({ queryKey: ["searches"] });
  return {
    create: useMutation({ mutationFn: (b: { name: string; params: SearchParams; alert_frequency: string }) => api.post("/me/searches", b), onSuccess: done }),
    update: useMutation({ mutationFn: ({ id, ...b }: { id: number; alert_frequency?: string; name?: string }) => api.patch(`/me/searches/${id}`, b), onSuccess: done }),
    remove: useMutation({ mutationFn: (id: number) => api.del(`/me/searches/${id}`), onSuccess: done }),
  };
}
export function useReadNotifications() {
  const qc = useQueryClient(); const done = () => qc.invalidateQueries({ queryKey: ["notifications"] });
  return { one: useMutation({ mutationFn: (id: number) => api.post(`/me/notifications/${id}/read`), onSuccess: done }), all: useMutation({ mutationFn: () => api.post("/me/notifications/read-all"), onSuccess: done }) };
}
