import axios, { AxiosInstance } from "axios";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
  timeout: 30000,
});

apiClient.interceptors.request.use((config) => {
  const projectId = window.localStorage.getItem("kuzuwiki.projectId") || "default";
  config.headers.set("X-Project-ID", projectId);
  return config;
});

export interface DashboardPanelLayout {
  id: "graph-overview" | "attack-index" | "entity-categories" | "source-reliability" | "claim-confidence";
  width: "half" | "wide";
}

export interface ProjectSummary {
  id: string;
  name: string;
  created_at: string;
  archived_at?: string | null;
  dashboard_layout: { version: 1; panels: DashboardPanelLayout[] };
}

export interface ProjectEntity {
  id: string;
  canonical_name: string;
  category?: string | null;
}

export interface CrossProjectLink {
  id: string;
  from_project_id: string;
  from_project_name: string;
  from_entity_id: string;
  from_entity_name: string;
  to_project_id: string;
  to_project_name: string;
  to_entity_id: string;
  to_entity_name: string;
  link_kind: "reference" | "possible_match" | "related_context" | "source_overlap";
  rationale: string;
  created_at: string;
}

export interface CreateProjectLinkPayload {
  source_entity_id: string;
  target_project_id: string;
  target_entity_id: string;
  link_kind: CrossProjectLink["link_kind"];
  rationale: string;
}

export interface SourceDocument {
  sha256: string;
  title?: string | null;
  domain?: string | null;
  published_at?: string | null;
  admiralty?: string | null;
  slop_score?: number | null;
  is_quarantined?: boolean;
}

export const projectsApi = {
  list: (includeArchived = false) => apiClient.get<{ projects: ProjectSummary[] }>("/projects", { params: { include_archived: includeArchived } }),
  create: (name: string) => apiClient.post<ProjectSummary>("/projects", { name }),
  archive: (projectId: string) => apiClient.post<ProjectSummary>(`/projects/${projectId}/archive`),
  restore: (projectId: string) => apiClient.post<ProjectSummary>(`/projects/${projectId}/restore`),
  delete: (projectId: string) => apiClient.delete(`/projects/${projectId}`),
  saveDashboard: (projectId: string, layout: ProjectSummary["dashboard_layout"]) =>
    apiClient.put<ProjectSummary>(`/projects/${projectId}/dashboard`, layout),
  entities: (projectId: string) => apiClient.get<{ entities: ProjectEntity[] }>(`/projects/${projectId}/entities`),
  links: (projectId: string) => apiClient.get<{ links: CrossProjectLink[] }>(`/projects/${projectId}/links`),
  createLink: (projectId: string, link: CreateProjectLinkPayload) =>
    apiClient.post<{ link: CrossProjectLink }>(`/projects/${projectId}/links`, link),
  deleteLink: (projectId: string, linkId: string) => apiClient.delete(`/projects/${projectId}/links/${linkId}`),
};

export const ingestApi = {
  documents: () => apiClient.get<{ documents: SourceDocument[]; count: number }>("/ingest/documents"),
  content: (sha256: string) => apiClient.get<string>(`/ingest/documents/${sha256}/content`, { responseType: "text" }),
  document: (formData: FormData) =>
    apiClient.post("/ingest/document", formData, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 600000,
    }),
};

export const graphApi = {
  subgraph: (entityId: string, hops = 2, limit = 100) =>
    apiClient.post("/graph/subgraph", { entity_id: entityId, hops, limit }),
  wikiMap: (limit = 250) => apiClient.get("/graph/wiki-map", { params: { limit } }),
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

export const statsApi = {
  dashboard: () => apiClient.get("/stats/dashboard"),
  graphHealth: () => apiClient.get("/stats/graph-health"),
};

export const queryApi = {
  compiled: (question: string, entityId?: string | null, saveToWiki = false) =>
    apiClient.post("/query/compiled", {
      question,
      entity_id: entityId || undefined,
      save_to_wiki: saveToWiki,
    }),
};

export const wsUrl = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws";
