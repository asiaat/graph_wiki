import React, { useCallback, useState } from "react";
import { Activity, Bot, Boxes, FileText, FolderTree, Moon, Network, PanelLeftOpen, Sun, X } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Group, Panel, Separator, usePanelRef, type Layout } from "react-resizable-panels";
import LeftPane, { type SidebarSection } from "./LeftPane";
import CenterPane from "./CenterPane";
import RightPane from "./RightPane";
import BottomDock from "./BottomDock";
import ProjectDashboard from "./ProjectDashboard";
import SourceDocumentView from "./SourceDocumentView";
import { projectsApi, type ProjectSummary, type SourceDocument } from "../../services/apiClient";

type BoardTab = "wiki" | "verification" | "infostream" | "dashboard";

const MAIN_TABS: { id: BoardTab; label: string; icon: React.ReactNode }[] = [
  { id: "wiki", label: "Wiki", icon: <FileText size={14} /> },
  { id: "verification", label: "JEV Verification", icon: <Network size={14} /> },
  { id: "infostream", label: "InfoStream", icon: <Activity size={14} /> },
  { id: "dashboard", label: "Dashboard", icon: <Activity size={14} /> },
];

const ACTIVITY_ITEMS: { id: SidebarSection; label: string; icon: React.ReactNode }[] = [
  { id: "projects", label: "Projects", icon: <Boxes size={19} /> },
  { id: "explorer", label: "Explorer", icon: <FolderTree size={19} /> },
  { id: "entities", label: "Kùzu Entities", icon: <Network size={19} /> },
  { id: "sources", label: "Sources", icon: <FilesIcon /> },
  { id: "agents", label: "Agent Queue", icon: <Bot size={19} /> },
];

function FilesIcon() {
  return <FileText size={19} />;
}

function initialBoardTab(): BoardTab {
  return window.location.hash === "#dashboard" ? "dashboard" : "wiki";
}

function initialSidebarLayout(): Layout {
  if (window.localStorage.getItem("kuzuwiki.sidebarCollapsed") === "true") {
    return { workspaceSidebar: 0, mainBoard: 100 };
  }
  try {
    const saved = JSON.parse(window.localStorage.getItem("kuzuwiki.sidebarLayout") || "null") as Layout | null;
    if (saved && Number.isFinite(saved.workspaceSidebar) && Number.isFinite(saved.mainBoard)) return saved;
  } catch {
    // Use the default IDE-style proportions when saved settings are invalid.
  }
  return { workspaceSidebar: 27, mainBoard: 73 };
}

export default function WorkbenchShell() {
  const [theme, setTheme] = useState<"light" | "dark">(
    () => window.localStorage.getItem("kuzuwiki.theme") === "dark" ? "dark" : "light",
  );
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState(
    () => window.localStorage.getItem("kuzuwiki.projectId") || "default",
  );
  const [activeBoardTab, setActiveBoardTab] = useState<BoardTab>(initialBoardTab);
  const [sidebarSection, setSidebarSection] = useState<SidebarSection>("explorer");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => window.localStorage.getItem("kuzuwiki.sidebarCollapsed") === "true",
  );
  const [sourceTabs, setSourceTabs] = useState<SourceDocument[]>([]);
  const [activeSourceSha, setActiveSourceSha] = useState<string | null>(null);
  const sidebarPanelRef = usePanelRef();
  const queryClient = useQueryClient();
  const { data: projects, refetch: refetchProjects } = useQuery({
    queryKey: ["projects"],
    queryFn: async () => (await projectsApi.list()).data.projects,
  });
  const { data: archivedProjects = [] } = useQuery({
    queryKey: ["projects", "with-archive"],
    queryFn: async () => (await projectsApi.list(true)).data.projects.filter((project) => Boolean(project.archived_at)),
  });
  const selectedProject = projects?.find((project) => project.id === selectedProjectId);

  React.useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    window.localStorage.setItem("kuzuwiki.theme", theme);
  }, [theme]);

  const setSelectedProject = useCallback((projectId: string) => {
    window.localStorage.setItem("kuzuwiki.projectId", projectId);
    queryClient.clear();
    setSelectedEntityId(null);
    setSourceTabs([]);
    setActiveSourceSha(null);
    setActiveBoardTab("wiki");
    setSelectedProjectId(projectId);
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
  }, [queryClient]);

  React.useEffect(() => {
    if (projects && !projects.some((project) => project.id === selectedProjectId)) setSelectedProject("default");
  }, [projects, selectedProjectId, setSelectedProject]);

  function selectMainTab(tab: BoardTab) {
    setActiveBoardTab(tab);
    setActiveSourceSha(null);
    const hash = tab === "dashboard" ? "#dashboard" : "";
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${hash}`);
  }

  function openSource(source: SourceDocument) {
    setSourceTabs((current) => current.some((item) => item.sha256 === source.sha256)
      ? current.map((item) => item.sha256 === source.sha256 ? source : item)
      : [...current, source]);
    setActiveSourceSha(source.sha256);
  }

  function closeSource(sha256: string) {
    setSourceTabs((current) => current.filter((source) => source.sha256 !== sha256));
    if (activeSourceSha === sha256) setActiveSourceSha(null);
  }

  function setMainAreaSource(source: SourceDocument) {
    openSource(source);
  }

  function toggleSidebar() {
    const nextCollapsed = !sidebarCollapsed;
    if (nextCollapsed) sidebarPanelRef.current?.collapse();
    else sidebarPanelRef.current?.expand();
    setSidebarCollapsed(nextCollapsed);
    window.localStorage.setItem("kuzuwiki.sidebarCollapsed", String(nextCollapsed));
  }

  function activateSidebarSection(section: SidebarSection) {
    setSidebarSection(section);
    if (sidebarCollapsed) toggleSidebar();
  }

  async function createProject() {
    const name = window.prompt("Name this project");
    if (!name?.trim()) return;
    try {
      const response = await projectsApi.create(name.trim());
      const created = response.data;
      queryClient.clear();
      setSelectedEntityId(null);
      setSourceTabs([]);
      setActiveSourceSha(null);
      setSelectedProjectId(created.id);
      window.localStorage.setItem("kuzuwiki.projectId", created.id);
      await refetchProjects();
      selectMainTab("dashboard");
    } catch {
      window.alert("Could not create the project. Please try again.");
    }
  }

  async function archiveProject(projectId: string) {
    try {
      await projectsApi.archive(projectId);
      if (projectId === selectedProjectId) setSelectedProject("default");
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
    } catch {
      window.alert("Could not archive this project. Please try again.");
    }
  }

  async function restoreProject(projectId: string) {
    try {
      await projectsApi.restore(projectId);
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
    } catch {
      window.alert("Could not restore this project. Please try again.");
    }
  }

  async function deleteProject(project: ProjectSummary) {
    const confirmed = window.confirm(`Permanently delete “${project.name}” and all of its graph, source, and wiki data? This cannot be undone.`);
    if (!confirmed) return;
    try {
      await projectsApi.delete(project.id);
      if (project.id === selectedProjectId) setSelectedProject("default");
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
    } catch {
      window.alert("Could not delete this project. Please try again.");
    }
  }

  function updateProject(updated: ProjectSummary) {
    queryClient.setQueryData<ProjectSummary[]>(["projects"], (current) =>
      current?.map((project) => project.id === updated.id ? updated : project),
    );
  }

  const activeSource = sourceTabs.find((source) => source.sha256 === activeSourceSha);

  return (
    <div className="flex h-screen flex-col bg-gray-50">
      <header className="flex shrink-0 items-center justify-between gap-4 border-b border-gray-200 bg-white px-4 py-2">
        <div className="flex min-w-0 items-center gap-3">
          <h1 className="shrink-0 text-lg font-bold text-gray-900">KuzuWiki-OSINT</h1>
          <span className="hidden truncate text-xs text-gray-400 xl:inline">Graph-Compiled Expert Intelligence</span>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="hidden max-w-48 truncate rounded bg-slate-100 px-2 py-1 text-xs text-slate-600 sm:block" title="Open the Projects pane" onClick={() => activateSidebarSection("projects")}>{selectedProject?.name || "Loading project…"}</button>
          <button
            type="button"
            className="rounded-md border border-gray-200 p-2 text-gray-600 hover:bg-gray-100 hover:text-gray-900"
            aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            aria-pressed={theme === "dark"}
            title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
          </button>
          <a href="/stats/graph-health" target="_blank" rel="noopener" className="rounded bg-green-50 px-2 py-1 text-xs text-green-700 hover:bg-green-100" title="Open graph health">Graph Health</a>
          <a href="/#attack-index" className="rounded bg-purple-50 px-2 py-1 text-xs text-purple-700 hover:bg-purple-100" title="Open Attack Index">Attack Index</a>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <nav className="z-10 flex w-12 shrink-0 flex-col items-center gap-1 border-r border-slate-200 bg-slate-900 py-2" aria-label="Workspace activity">
          {ACTIVITY_ITEMS.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-label={item.label}
              aria-pressed={sidebarSection === item.id}
              title={item.label}
              onClick={() => activateSidebarSection(item.id)}
              className={`relative flex h-10 w-10 items-center justify-center rounded-md ${sidebarSection === item.id ? "bg-slate-700 text-white" : "text-slate-400 hover:bg-slate-800 hover:text-white"}`}
            >
              {sidebarSection === item.id && <span className="absolute left-0 h-6 w-0.5 rounded-r bg-blue-400" />}
              {item.icon}
            </button>
          ))}
          {sidebarCollapsed && (
            <button type="button" className="mt-auto rounded p-2 text-slate-400 hover:bg-slate-800 hover:text-white" aria-label="Open workspace sidebar" title="Open workspace sidebar" onClick={toggleSidebar}>
              <PanelLeftOpen size={18} />
            </button>
          )}
        </nav>

        <Group
          id="workspace-layout"
          orientation="horizontal"
          className="min-h-0 min-w-0 flex-1 overflow-hidden"
          defaultLayout={initialSidebarLayout()}
          onLayoutChanged={(layout, meta) => {
            if (meta.isUserInteraction) window.localStorage.setItem("kuzuwiki.sidebarLayout", JSON.stringify(layout));
          }}
        >
          <Panel
            id="workspaceSidebar"
            panelRef={sidebarPanelRef}
            defaultSize={27}
            minSize={18}
            collapsedSize={0}
            collapsible
            onResize={(size) => {
              const collapsed = size.asPercentage < 1;
              setSidebarCollapsed(collapsed);
              window.localStorage.setItem("kuzuwiki.sidebarCollapsed", String(collapsed));
            }}
          >
            <LeftPane
              section={sidebarSection}
              projects={projects ?? []}
              archivedProjects={archivedProjects}
              selectedProjectId={selectedProjectId}
              selectedEntityId={selectedEntityId}
              selectedSourceSha={activeSourceSha}
              onSelectEntity={(entityId) => { setSelectedEntityId(entityId); selectMainTab("wiki"); }}
              onSelectProject={setSelectedProject}
              onNewProject={() => void createProject()}
              onArchiveProject={(projectId) => void archiveProject(projectId)}
              onRestoreProject={(projectId) => void restoreProject(projectId)}
              onDeleteProject={(project) => void deleteProject(project)}
              onOpenSource={setMainAreaSource}
              onCollapse={toggleSidebar}
            />
          </Panel>
          <Separator className="w-1 bg-slate-200 transition-colors hover:bg-blue-400" />
          <Panel id="mainBoard" defaultSize={73} minSize={35}>
            <main className="flex h-full min-h-0 flex-col bg-white" aria-label="Main work area">
              <div className="flex h-10 shrink-0 items-stretch overflow-x-auto border-b border-slate-200 bg-slate-100" role="tablist" aria-label="Main work area tabs">
                {MAIN_TABS.map((tab) => (
                  <button key={tab.id} type="button" role="tab" aria-selected={activeBoardTab === tab.id && activeSourceSha === null} onClick={() => selectMainTab(tab.id)} className={`flex shrink-0 items-center gap-2 border-r border-slate-200 px-3 text-xs ${activeBoardTab === tab.id && activeSourceSha === null ? "border-t-2 border-t-blue-600 bg-white font-medium text-slate-900" : "border-t-2 border-t-transparent text-slate-500 hover:bg-slate-50 hover:text-slate-800"}`}>
                    {tab.icon}{tab.label}
                  </button>
                ))}
                {sourceTabs.map((source) => (
                  <div key={source.sha256} role="presentation" className={`flex shrink-0 items-center border-r border-slate-200 border-t-2 ${activeSourceSha === source.sha256 ? "border-t-blue-600 bg-white" : "border-t-transparent bg-slate-100"}`}>
                    <button type="button" role="tab" aria-selected={activeSourceSha === source.sha256} title={source.title || source.domain || source.sha256} onClick={() => setActiveSourceSha(source.sha256)} className="max-w-48 truncate px-3 text-xs text-slate-700">{source.title || source.domain || "Source"}</button>
                    <button type="button" aria-label={`Close ${source.title || "source tab"}`} className="mr-1 rounded p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700" onClick={() => closeSource(source.sha256)}><X size={12} /></button>
                  </div>
                ))}
              </div>
              <div className="min-h-0 flex-1 overflow-hidden">
                {activeSource ? <SourceDocumentView source={activeSource} /> : activeBoardTab === "wiki" ? (
                  <CenterPane entityId={selectedEntityId} onSelectEntity={setSelectedEntityId} />
                ) : activeBoardTab === "verification" ? (
                  <div className="h-full overflow-y-auto"><RightPane entityId={selectedEntityId} /></div>
                ) : activeBoardTab === "infostream" ? (
                  <BottomDock />
                ) : selectedProject ? (
                  <ProjectDashboard project={selectedProject} projects={projects ?? []} onSelectProject={setSelectedProject} onProjectUpdated={updateProject} />
                ) : (
                  <div className="p-8 text-sm text-slate-500">Loading project dashboard…</div>
                )}
              </div>
            </main>
          </Panel>
        </Group>
      </div>
    </div>
  );
}
