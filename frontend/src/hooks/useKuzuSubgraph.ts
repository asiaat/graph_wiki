import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, useCallback } from "react";
import { graphApi, osintApi, wikiApi, wsUrl } from "../services/apiClient";
import type {
  AttackIndexTimeSeries,
  Entity,
  LintReport,
  SubgraphResponse,
  WikiPage,
} from "../types/jevGraph";

type WebSocketMessage =
  | { type: "system"; event: "connected" | "heartbeat" | "disconnected"; data: Record<string, unknown> }
  | { type: "mutation"; event: "entity_created" | "entity_updated" | "claim_created" | "relation_created" | "contradiction_detected"; data: Record<string, unknown> }
  | { type: "task"; event: "started" | "completed" | "failed"; data: Record<string, unknown> };

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

export function useWikiMap(limit = 250) {
  return useQuery<SubgraphResponse>({
    queryKey: ["wiki-map", limit],
    queryFn: () => graphApi.wikiMap(limit).then((r) => r.data),
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
 * Connects to the backend WebSocket at /ws and handles:
 * - Connection lifecycle (open/close/reconnect)
 * - Entity/claim/relation mutations
 * - Contradiction alerts from the linter
 * - Task completion events from the worker
 */
export function useWebSocket(
  entityId: string,
  options?: {
    onMessage?: (msg: WebSocketMessage) => void;
    onConnect?: () => void;
    onDisconnect?: () => void;
    reconnectInterval?: number;
    maxReconnectAttempts?: number;
  }
): { connected: boolean; lastMessage: WebSocketMessage | null; send: (msg: unknown) => void } {
  const socketRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const closedSocketsRef = useRef(new WeakSet<WebSocket>());

  const {
    onMessage,
    onConnect,
    onDisconnect,
    reconnectInterval = 5000,
    maxReconnectAttempts = 10,
  } = options || {};

  const connect = useCallback(() => {
    if (!entityId || typeof WebSocket === "undefined") return;
    if (socketRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const socket = new WebSocket(`${wsUrl}?entity_id=${encodeURIComponent(entityId)}`);
      socketRef.current = socket;

      socket.onopen = () => {
        if (closedSocketsRef.current.has(socket)) return;
        setConnected(true);
        reconnectAttemptsRef.current = 0;
        onConnect?.();
      };

      socket.onclose = () => {
        if (closedSocketsRef.current.has(socket)) return;
        setConnected(false);
        onDisconnect?.();

        // Attempt reconnection with exponential backoff
        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          const delay = Math.min(reconnectInterval * Math.pow(1.5, reconnectAttemptsRef.current), 60000);
          reconnectAttemptsRef.current += 1;
          reconnectTimeoutRef.current = window.setTimeout(connect, delay);
        }
      };

      socket.onerror = () => {
        if (closedSocketsRef.current.has(socket)) return;
        setConnected(false);
      };

      socket.onmessage = (event) => {
        if (closedSocketsRef.current.has(socket)) return;
        try {
          const msg = JSON.parse(event.data) as WebSocketMessage;
          setLastMessage(msg);
          onMessage?.(msg);
        } catch {
          // Ignore non-JSON messages
        }
      };
    } catch {
      setConnected(false);
    }
  }, [entityId, onMessage, onConnect, onDisconnect, reconnectInterval, maxReconnectAttempts]);

  const send = useCallback((msg: unknown) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(msg));
    }
  }, []);

  useEffect(() => {
    const closedSockets = closedSocketsRef.current;
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        window.clearTimeout(reconnectTimeoutRef.current);
      }
      const socket = socketRef.current;
      socketRef.current = null;
      if (socket) {
        closedSockets.add(socket);
        socket.close();
      }
    };
  }, [connect]);

  return { connected, lastMessage, send };
}
