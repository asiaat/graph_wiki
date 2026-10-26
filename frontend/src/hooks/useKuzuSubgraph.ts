import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient, graphApi, wikiApi, osintApi, wsUrl } from "./apiClient";
import { Entity, SubgraphResponse, GraphEdge, WikiPage, AttackIndexTimeSeries } from "../types/jevGraph";

export function useEntity(entityId: string) {
  return useQuery({
    queryKey: ["entity", entityId],
    queryFn: () => graphApi.getEntity(entityId).then((r) => r.data),
    enabled: !!entityId,
  });
}

export function useSubgraph(entityId: string, hops = 2) {
  return useQuery<SubgraphResponse>({
    queryKey: ["subgraph", entityId, hops],
    queryFn: () => graphApi.subgraph(entityId, hops).then((r) => r.data),
    enabled: !!entityId,
  });
}

export function useWikiPage(slug: string) {
  return useQuery<WikiPage>({
    queryKey: ["wiki", slug],
    queryFn: () => wikiApi.getPage(slug).then((r) => r.data),
    enabled: !!slug,
  });
}

export function useEntityWiki(entityId: string) {
  return useQuery<WikiPage>({
    queryKey: ["entityWiki", entityId],
    queryFn: () => wikiApi.getEntityWiki(entityId).then((r) => r.data),
    enabled: !!entityId,
  });
}

export function useAttackIndex(days = 30) {
  return useQuery<AttackIndexTimeSeries>({
    queryKey: ["attackIndex", days],
    queryFn: () => osintApi.attackIndex(undefined, days).then((r) => r.data),
    refetchInterval: 60000,
  });
}

export function useContradictions() {
  return useQuery({
    queryKey: ["contradictions"],
    queryFn: () => osintApi.contradictions().then((r) => r.data),
    refetchInterval: 30000,
  });
}

export function useComplicateEntity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (entityId: string) => osintApi.complicate(entityId).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subgraph"] });
    },
  });
}

export function useWebSocket(entityId: string) {
  // WebSocket hook for live graph mutations
  // Implementation would connect to wsUrl and subscribe to entity updates
}