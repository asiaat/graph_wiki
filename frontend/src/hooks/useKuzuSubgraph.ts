import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { graphApi, osintApi, wikiApi, wsUrl } from "../services/apiClient";
import type {
  AttackIndexTimeSeries,
  Entity,
  LintReport,
  SubgraphResponse,
  WikiPage,
} from "../types/jevGraph";

export function useEntity(entityId: string) {
  return useQuery<{ entity: Entity }>({
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
  return useQuery<LintReport>({
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
      queryClient.invalidateQueries({ queryKey: ["contradictions"] });
    },
  });
}

/**
 * Subscribe to live graph mutations for one entity.
 *
 * The backend has no WebSocket endpoint yet, so the hook degrades to a no-op
 * instead of throwing: the returned `connected` flag tells the UI whether
 * live updates are actually available.
 */
export function useWebSocket(entityId: string): { connected: boolean } {
  const socketRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!entityId || typeof WebSocket === "undefined") return;
    let closed = false;
    try {
      const socket = new WebSocket(`${wsUrl}?entity_id=${encodeURIComponent(entityId)}`);
      socketRef.current = socket;
      socket.onopen = () => !closed && setConnected(true);
      socket.onclose = () => !closed && setConnected(false);
      socket.onerror = () => !closed && setConnected(false);
    } catch {
      setConnected(false);
    }
    return () => {
      closed = true;
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [entityId]);

  return { connected };
}
