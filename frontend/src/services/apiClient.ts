import axios, { AxiosInstance } from "axios";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
  timeout: 30000,
});

export const ingestApi = {
  document: (formData: FormData) => apiClient.post("/ingest/document", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  }),
};

export const graphApi = {
  subgraph: (entityId: string, hops = 2, limit = 100) =>
    apiClient.post("/graph/subgraph", { entity_id: entityId, hops, limit }),
  shortestPath: (source: string, target: string, maxHops = 5) =>
    apiClient.post("/graph/shortest-path", { source_id: source, target_id: target, max_hops: maxHops }),
  clusters: (category?: string, minSize = 3) =>
    apiClient.post("/graph/clusters", { category, min_size: minSize }),
  getEntity: (id: string) => apiClient.get(`/graph/entity/${id}`),
};

export const wikiApi = {
  getPage: (slug: string) => apiClient.get(`/wiki/${slug}`),
  getEntityWiki: (entityId: string) => apiClient.get(`/wiki/entity/${entityId}`),
  saveQuery: (slug: string, content: string) =>
    apiClient.put(`/wiki/${slug}`, content, { params: { save_to_wiki: true } }),
};

export const osintApi = {
  complicate: (entityId: string) => apiClient.post(`/osint/complicate/${entityId}`),
  attackIndex: (topic?: string, days = 30) =>
    apiClient.get("/osint/attack-index", { params: { topic, days } }),
  contradictions: () => apiClient.get("/osint/lint/contradictions"),
};

export const wsUrl = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws";