import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, Check, Pencil, Plus, Save, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import AttackIndexWave from "../analytics/AttackIndexWave";
import GraphOverviewChart from "../analytics/GraphOverviewChart";
import EntityCategoryChart from "../analytics/EntityCategoryChart";
import AdmiraltyBreakdownChart from "../analytics/AdmiraltyBreakdownChart";
import ClaimConfidenceChart from "../analytics/ClaimConfidenceChart";
import FullscreenFrame from "./FullscreenFrame";
import CrossProjectLinks from "./CrossProjectLinks";
import { projectsApi, statsApi } from "../../services/apiClient";
import type { DashboardPanelLayout, ProjectSummary } from "../../services/apiClient";
import type { DashboardStats } from "../../types/jevGraph";

interface ProjectDashboardProps {
  project: ProjectSummary;
  projects: ProjectSummary[];
  onSelectProject: (projectId: string) => void;
  onProjectUpdated: (project: ProjectSummary) => void;
}

const PANEL_LABELS: Record<DashboardPanelLayout["id"], string> = {
  "graph-overview": "Graph Overview",
  "attack-index": "Attack Index",
  "entity-categories": "Entity Categories",
  "source-reliability": "Source Reliability",
  "claim-confidence": "Claim Confidence",
};

const ALL_PANELS = Object.keys(PANEL_LABELS) as DashboardPanelLayout["id"][];

export default function ProjectDashboard({ project, projects, onSelectProject, onProjectUpdated }: ProjectDashboardProps) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [panels, setPanels] = useState(project.dashboard_layout.panels);
  const { data: stats, isLoading, error } = useQuery<DashboardStats>({
    queryKey: ["stats", "dashboard"],
    queryFn: async () => (await statsApi.dashboard()).data as DashboardStats,
    refetchInterval: 30000,
  });

  useEffect(() => {
    setPanels(project.dashboard_layout.panels);
    setEditing(false);
  }, [project.id, project.dashboard_layout]);

  function addPanel(id: DashboardPanelLayout["id"]) {
    setPanels((current) => [...current, { id, width: "half" }]);
  }

  function removePanel(id: DashboardPanelLayout["id"]) {
    setPanels((current) => current.filter((panel) => panel.id !== id));
  }

  function movePanel(index: number, direction: -1 | 1) {
    setPanels((current) => {
      const next = [...current];
      const target = index + direction;
      if (target < 0 || target >= next.length) return current;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  async function saveLayout() {
    setSaving(true);
    setSaveError("");
    try {
      const response = await projectsApi.saveDashboard(project.id, { version: 1, panels });
      onProjectUpdated(response.data);
      setEditing(false);
    } catch {
      setSaveError("Could not save this project dashboard. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="h-full overflow-y-auto bg-slate-50 p-4 md:p-7">
      <div className="mx-auto max-w-7xl">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">Project dashboard</p>
            <h1 className="mt-1 text-2xl font-bold text-slate-900">{project.name}</h1>
            <p className="mt-1 text-sm text-slate-600">Project data and saved dashboard layout are isolated from other projects.</p>
          </div>
          {editing ? (
            <div className="flex gap-2">
              <button className="btn btn-secondary btn-sm" onClick={() => { setPanels(project.dashboard_layout.panels); setEditing(false); }}>
                <X size={14} className="mr-1" /> Cancel
              </button>
              <button className="btn btn-primary btn-sm" disabled={saving} onClick={() => void saveLayout()}>
                {saving ? <Check size={14} className="mr-1" /> : <Save size={14} className="mr-1" />}
                {saving ? "Saving…" : "Save layout"}
              </button>
            </div>
          ) : (
            <button className="btn btn-secondary btn-sm" onClick={() => setEditing(true)}>
              <Pencil size={14} className="mr-1" /> Customize dashboard
            </button>
          )}
        </div>

        <CrossProjectLinks project={project} projects={projects} onSelectProject={onSelectProject} />

        {editing && (
          <section className="mb-5 rounded-xl border border-blue-200 bg-white p-4 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-900">Arrange dashboard panels</h2>
            <p className="mt-1 text-xs text-slate-600">Add or remove panels, change their order, and choose half or full width. The layout is saved for this project.</p>
            {panels.length > 0 && (
              <ol className="mt-3 space-y-2">
                {panels.map((panel, index) => (
                  <li key={panel.id} className="flex flex-wrap items-center gap-2 rounded border border-slate-200 px-3 py-2">
                    <span className="min-w-36 flex-1 text-sm">{PANEL_LABELS[panel.id]}</span>
                    <select
                      aria-label={`${PANEL_LABELS[panel.id]} width`}
                      className="input input-sm"
                      value={panel.width}
                      onChange={(event) => setPanels((current) => current.map((item) => item.id === panel.id ? { ...item, width: event.target.value as DashboardPanelLayout["width"] } : item))}
                    >
                      <option value="half">Half width</option>
                      <option value="wide">Full width</option>
                    </select>
                    <button className="btn btn-secondary btn-sm" aria-label={`Move ${PANEL_LABELS[panel.id]} up`} disabled={index === 0} onClick={() => movePanel(index, -1)}><ArrowUp size={14} /></button>
                    <button className="btn btn-secondary btn-sm" aria-label={`Move ${PANEL_LABELS[panel.id]} down`} disabled={index === panels.length - 1} onClick={() => movePanel(index, 1)}><ArrowDown size={14} /></button>
                    <button className="btn btn-secondary btn-sm" aria-label={`Remove ${PANEL_LABELS[panel.id]}`} onClick={() => removePanel(panel.id)}><X size={14} /> <span className="ml-1">Remove</span></button>
                  </li>
                ))}
              </ol>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              {ALL_PANELS.filter((id) => !panels.some((panel) => panel.id === id)).map((id) => (
                <button key={id} className="btn btn-secondary btn-sm" onClick={() => addPanel(id)}><Plus size={14} className="mr-1" />{PANEL_LABELS[id]}</button>
              ))}
              {panels.length === 0 && <p className="self-center text-xs text-slate-500">No panels selected. Add one to start building this dashboard.</p>}
            </div>
            {saveError && <p role="alert" className="mt-3 text-sm text-red-700">{saveError}</p>}
          </section>
        )}

        {isLoading && <p className="rounded-lg bg-white p-5 text-sm text-slate-500">Loading project statistics…</p>}
        {error && <p role="alert" className="rounded-lg bg-white p-5 text-sm text-red-700">Could not load project statistics.</p>}
        {!isLoading && !error && stats && panels.length === 0 && !editing && (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
            <p className="text-sm text-slate-600">This dashboard has no panels yet.</p>
            <button className="btn btn-primary btn-sm mt-3" onClick={() => setEditing(true)}>Add dashboard panels</button>
          </div>
        )}
        {!isLoading && !error && stats && (
          <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
            {panels.map((panel) => (
              <div key={panel.id} className={panel.width === "wide" ? "lg:col-span-2" : ""}>
                <FullscreenFrame title={PANEL_LABELS[panel.id]} className="min-h-72 rounded-xl border border-slate-200 bg-white shadow-sm" fullscreenClassName="overflow-auto bg-white p-5">
                  {panel.id === "graph-overview" && <GraphOverviewChart stats={stats} title="Graph Overview" height={320} />}
                  {panel.id === "attack-index" && <AttackIndexWave />}
                  {panel.id === "entity-categories" && <EntityCategoryChart data={stats.entities.by_category} height={300} />}
                  {panel.id === "source-reliability" && <AdmiraltyBreakdownChart data={stats.sources.admiralty_breakdown} height={300} />}
                  {panel.id === "claim-confidence" && <ClaimConfidenceChart data={stats.claims.confidence_distribution} height={300} />}
                </FullscreenFrame>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
