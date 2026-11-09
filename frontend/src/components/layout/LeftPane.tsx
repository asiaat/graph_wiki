import { useEffect, useState } from "react";
import { Archive, Bot, Boxes, Database, FileText, FolderOpen, Network, PanelLeftClose, Plus, RotateCcw, Trash2 } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiClient, ingestApi, type ProjectSummary, type SourceDocument } from "../../services/apiClient";
import SourceImportPanel from "./SourceImportPanel";
import type { EntityCounts } from "../../types/jevGraph";

export type SidebarSection = "projects" | "explorer" | "entities" | "sources" | "agents";

interface LeftPaneProps {
  section: SidebarSection;
  projects: ProjectSummary[];
  archivedProjects: ProjectSummary[];
  selectedProjectId: string;
  selectedEntityId: string | null;
  selectedSourceSha: string | null;
  onSelectEntity: (entityId: string) => void;
  onSelectProject: (projectId: string) => void;
  onNewProject: () => void;
  onArchiveProject: (projectId: string) => void;
  onRestoreProject: (projectId: string) => void;
  onDeleteProject: (project: ProjectSummary) => void;
  onOpenSource: (source: SourceDocument) => void;
  onCollapse: () => void;
}

export default function LeftPane({
  section,
  projects,
  archivedProjects,
  selectedProjectId,
  selectedEntityId,
  selectedSourceSha,
  onSelectEntity,
  onSelectProject,
  onNewProject,
  onArchiveProject,
  onRestoreProject,
  onDeleteProject,
  onOpenSource,
  onCollapse,
}: LeftPaneProps) {
  const [showArchived, setShowArchived] = useState(false);
  const { data: entities } = useQuery({
    queryKey: ["entities", "count"],
    queryFn: async () => (await apiClient.get("/graph/entities/count")).data as EntityCounts,
  });
  const { data: entityList } = useQuery({
    queryKey: ["entities", "list"],
    queryFn: async () => (await apiClient.get("/graph/entities")).data as {
      entities: { id: string; canonical_name: string; category?: string }[];
    },
  });
  const { data: sourceData } = useQuery({
    queryKey: ["docs", "list"],
    queryFn: async () => (await ingestApi.documents()).data,
  });

  useEffect(() => {
    if (!selectedEntityId && entityList?.entities.length) onSelectEntity(entityList.entities[0].id);
  }, [entityList, onSelectEntity, selectedEntityId]);

  const entitiesView = (
    <div className="space-y-1 px-2 pb-4">
      {(entityList?.entities ?? []).map((entity) => (
        <button
          key={entity.id}
          type="button"
          onClick={() => onSelectEntity(entity.id)}
          className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs ${selectedEntityId === entity.id ? "bg-blue-50 font-medium text-blue-700" : "text-slate-700 hover:bg-slate-100"}`}
          title={entity.id}
        >
          <Network size={13} className="shrink-0 text-slate-400" />
          <span className="min-w-0 flex-1 truncate">{entity.canonical_name}</span>
          {entity.category && <span className="shrink-0 text-[10px] text-slate-400">{entity.category}</span>}
        </button>
      ))}
      {entityList && entityList.entities.length === 0 && <p className="px-2 py-3 text-xs text-slate-500">No compiled entities yet.</p>}
    </div>
  );

  const sourcesView = (
    <div className="space-y-1 px-2 pb-4">
      {(sourceData?.documents ?? []).map((source) => (
        <button
          key={source.sha256}
          type="button"
          onClick={() => onOpenSource(source)}
          className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs ${selectedSourceSha === source.sha256 ? "bg-blue-50 font-medium text-blue-700" : "text-slate-700 hover:bg-slate-100"}`}
          title={`${source.title || source.domain || "Source"} · ${source.sha256}`}
        >
          <FileText size={13} className="shrink-0 text-slate-400" />
          <span className="min-w-0 flex-1 truncate">{source.title || source.domain || source.sha256.slice(0, 16)}</span>
          {source.is_quarantined && <span className="shrink-0 text-[10px] text-amber-700">Review</span>}
        </button>
      ))}
      {sourceData && sourceData.documents.length === 0 && <p className="px-2 py-3 text-xs text-slate-500">Uploaded sources will appear here.</p>}
    </div>
  );

  const titles: Record<SidebarSection, string> = {
    projects: "Projects",
    explorer: "Explorer",
    entities: "Kùzu Entities",
    sources: "Source Vault",
    agents: "Agent Queue",
  };

  return (
    <aside className="flex h-full min-w-0 flex-col border-r border-slate-200 bg-white" aria-label="Workspace explorer">
      <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          {section === "projects" ? <Boxes size={15} className="text-blue-600" /> : section === "explorer" ? <FolderOpen size={15} className="text-blue-600" /> : section === "entities" ? <Network size={15} className="text-blue-600" /> : section === "sources" ? <FileText size={15} className="text-blue-600" /> : <Bot size={15} className="text-blue-600" />}
          <h2 className="truncate text-xs font-semibold uppercase tracking-wide text-slate-700">{titles[section]}</h2>
        </div>
        <button type="button" className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Close sidebar to icons" title="Close sidebar to icons" onClick={onCollapse}>
          <PanelLeftClose size={16} />
        </button>
      </div>

      <div className={`shrink-0 px-2 pt-2 ${section === "explorer" || section === "sources" ? "" : "hidden"}`}>
        <SourceImportPanel />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto py-2">
        {section === "projects" && (
          <div className="space-y-1 px-2">
            <button type="button" className="mb-2 flex w-full items-center gap-2 rounded border border-dashed border-slate-300 px-2 py-2 text-left text-xs font-medium text-slate-600 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700" onClick={onNewProject}>
              <Plus size={14} /> New project
            </button>
            {projects.map((project) => (
              <div key={project.id} className="group flex items-center gap-1">
                <button type="button" onClick={() => onSelectProject(project.id)} className={`flex min-w-0 flex-1 items-center gap-2 rounded px-2 py-2 text-left text-xs ${selectedProjectId === project.id ? "bg-blue-50 font-semibold text-blue-700" : "text-slate-700 hover:bg-slate-100"}`}>
                  <Boxes size={14} className="shrink-0 text-slate-400" />
                  <span className="min-w-0 flex-1 truncate">{project.name}</span>
                  {selectedProjectId === project.id && <span className="text-[10px] text-blue-500">Open</span>}
                </button>
                {project.id !== "default" && (
                  <>
                    <button type="button" aria-label={`Archive ${project.name}`} title={`Archive ${project.name}`} className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-amber-700" onClick={() => onArchiveProject(project.id)}><Archive size={13} /></button>
                    <button type="button" aria-label={`Delete ${project.name}`} title={`Delete ${project.name}`} className="rounded p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-700" onClick={() => onDeleteProject(project)}><Trash2 size={13} /></button>
                  </>
                )}
              </div>
            ))}
            {projects.length === 0 && <p className="px-2 py-3 text-xs text-slate-500">Loading projects…</p>}
            <button type="button" className="mt-3 flex w-full items-center justify-between rounded px-2 py-2 text-left text-xs text-slate-600 hover:bg-slate-100" aria-expanded={showArchived} onClick={() => setShowArchived((value) => !value)}>
              <span>{showArchived ? "Hide archived" : "Show archived"}</span>
              <span className="text-[10px] text-slate-400">{archivedProjects.length}</span>
            </button>
            {showArchived && archivedProjects.map((project) => (
              <div key={project.id} className="flex items-center gap-1 rounded bg-slate-50 px-2 py-2 text-xs text-slate-600">
                <Archive size={13} className="shrink-0 text-slate-400" />
                <span className="min-w-0 flex-1 truncate" title={project.name}>{project.name}</span>
                <button type="button" aria-label={`Restore ${project.name}`} title={`Restore ${project.name}`} className="rounded p-1 text-slate-400 hover:bg-green-50 hover:text-green-700" onClick={() => onRestoreProject(project.id)}><RotateCcw size={13} /></button>
                <button type="button" aria-label={`Delete ${project.name}`} title={`Delete ${project.name}`} className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-700" onClick={() => onDeleteProject(project)}><Trash2 size={13} /></button>
              </div>
            ))}
            <p className="mt-3 px-2 text-[10px] leading-4 text-slate-400">Each project has its own graph, source vault, and dashboard.</p>
          </div>
        )}
        {section === "explorer" && (
          <div className="space-y-3 px-2">
            <div className="px-2 pt-1">
              <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                <span>Workspace</span><span>{entities?.total ?? 0} entities · {sourceData?.count ?? 0} sources</span>
              </div>
            </div>
            <details open className="text-xs">
              <summary className="cursor-pointer rounded px-2 py-1.5 font-semibold text-slate-700 hover:bg-slate-50">Sources <span className="font-normal text-slate-400">({sourceData?.count ?? 0})</span></summary>
              {sourcesView}
            </details>
            <details open className="text-xs">
              <summary className="cursor-pointer rounded px-2 py-1.5 font-semibold text-slate-700 hover:bg-slate-50">Kùzu Entities <span className="font-normal text-slate-400">({entities?.total ?? 0})</span></summary>
              {entitiesView}
            </details>
          </div>
        )}
        {section === "entities" && entitiesView}
        {section === "sources" && (
          sourcesView
        )}
        {section === "agents" && (
          <div className="space-y-1 px-3 text-xs text-slate-700">
            {[
              ["Gatekeeper", "Source quality and Admiralty review"],
              ["Lande HVG", "Term and hierarchy analysis"],
              ["JEV Swarm", "Three expert extractors"],
              ["Wiki Compiler", "Evidence-backed dossiers"],
              ["Adversarial Linter", "Contradiction and gap checks"],
            ].map(([name, description]) => (
              <div key={name} className="rounded px-2 py-2 hover:bg-slate-50">
                <div className="flex items-center gap-2 font-medium"><Bot size={13} className="text-slate-400" />{name}</div>
                <p className="pl-5 pt-1 text-[10px] text-slate-500">{description}</p>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="border-t border-slate-200 px-3 py-2 text-[10px] text-slate-400">
        {section === "projects" ? `${projects.length} projects` : section === "entities" ? `${entities?.total ?? 0} compiled entity nodes` : section === "sources" ? `${sourceData?.count ?? 0} archived source files` : "Project workspace"}
        {section === "explorer" && <span className="ml-1 inline-flex items-center gap-1"><Database size={10} />KùzuDB</span>}
      </div>
    </aside>
  );
}
