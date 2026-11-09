import { useEffect, useState, type FormEvent } from "react";
import { ArrowLeftRight, ExternalLink, Link2, Unlink } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { projectsApi } from "../../services/apiClient";
import type { CrossProjectLink, ProjectEntity, ProjectSummary } from "../../services/apiClient";

interface CrossProjectLinksProps {
  project: ProjectSummary;
  projects: ProjectSummary[];
  onSelectProject: (projectId: string) => void;
}

const LINK_KIND_LABELS: Record<CrossProjectLink["link_kind"], string> = {
  reference: "Reference",
  possible_match: "Possible match",
  related_context: "Related context",
  source_overlap: "Source overlap",
};

function entityLabel(entity: ProjectEntity) {
  return entity.category ? `${entity.canonical_name} · ${entity.category}` : entity.canonical_name;
}

export default function CrossProjectLinks({ project, projects, onSelectProject }: CrossProjectLinksProps) {
  const queryClient = useQueryClient();
  const otherProjects = projects.filter((candidate) => candidate.id !== project.id);
  const [targetProjectId, setTargetProjectId] = useState("");
  const [sourceEntityId, setSourceEntityId] = useState("");
  const [targetEntityId, setTargetEntityId] = useState("");
  const [linkKind, setLinkKind] = useState<CrossProjectLink["link_kind"]>("reference");
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const { data: sourceEntities } = useQuery({
    queryKey: ["project-entities", project.id],
    queryFn: async () => (await projectsApi.entities(project.id)).data.entities,
  });
  const { data: targetEntities } = useQuery({
    queryKey: ["project-entities", targetProjectId],
    queryFn: async () => (await projectsApi.entities(targetProjectId)).data.entities,
    enabled: Boolean(targetProjectId),
  });
  const { data: links } = useQuery({
    queryKey: ["project-links", project.id],
    queryFn: async () => (await projectsApi.links(project.id)).data.links,
  });

  useEffect(() => {
    if (otherProjects.length && !otherProjects.some((candidate) => candidate.id === targetProjectId)) {
      setTargetProjectId(otherProjects[0].id);
    }
  }, [otherProjects, targetProjectId]);
  useEffect(() => {
    if (sourceEntities?.length && !sourceEntities.some((entity) => entity.id === sourceEntityId)) {
      setSourceEntityId(sourceEntities[0].id);
    }
  }, [sourceEntities, sourceEntityId]);
  useEffect(() => {
    if (targetEntities?.length && !targetEntities.some((entity) => entity.id === targetEntityId)) {
      setTargetEntityId(targetEntities[0].id);
    }
  }, [targetEntities, targetEntityId]);

  async function createLink(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!targetProjectId || !sourceEntityId || !targetEntityId || busy) return;
    setBusy(true);
    setMessage("");
    try {
      await projectsApi.createLink(project.id, {
        source_entity_id: sourceEntityId,
        target_project_id: targetProjectId,
        target_entity_id: targetEntityId,
        link_kind: linkKind,
        rationale: rationale.trim(),
      });
      await queryClient.invalidateQueries({ queryKey: ["project-links", project.id] });
      setRationale("");
      setMessage("Project reference saved.");
    } catch (error) {
      const response = (error as { response?: { data?: { detail?: string } } }).response;
      setMessage(response?.data?.detail || "Could not save this cross-project reference.");
    } finally {
      setBusy(false);
    }
  }

  async function removeLink(linkId: string) {
    setBusy(true);
    setMessage("");
    try {
      await projectsApi.deleteLink(project.id, linkId);
      await queryClient.invalidateQueries({ queryKey: ["project-links", project.id] });
      setMessage("Project reference removed.");
    } catch {
      setMessage("Could not remove this project reference.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mb-5 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <ArrowLeftRight size={18} className="mt-0.5 text-indigo-700" />
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Cross-project links</h2>
          <p className="mt-1 max-w-4xl text-xs leading-5 text-slate-600">
            Connect entities across separate project databases. These are analyst references: they do not copy data, merge entities, or count as verified graph relations.
          </p>
        </div>
      </div>

      {otherProjects.length > 0 ? (
        sourceEntities?.length && targetEntities?.length ? (
          <form className="mt-4 grid grid-cols-1 items-end gap-3 md:grid-cols-2 xl:grid-cols-5" onSubmit={(event) => void createLink(event)}>
            <label className="text-xs font-medium text-slate-700">
              This project entity
              <select className="input mt-1 w-full text-xs" aria-label="Source project entity" value={sourceEntityId} onChange={(event) => setSourceEntityId(event.target.value)}>
                {sourceEntities.map((entity) => <option key={entity.id} value={entity.id}>{entityLabel(entity)}</option>)}
              </select>
            </label>
            <label className="text-xs font-medium text-slate-700">
              Other project
              <select className="input mt-1 w-full text-xs" aria-label="Target project" value={targetProjectId} onChange={(event) => { setTargetProjectId(event.target.value); setTargetEntityId(""); }}>
                {otherProjects.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.name}</option>)}
              </select>
            </label>
            <label className="text-xs font-medium text-slate-700">
              Other project entity
              <select className="input mt-1 w-full text-xs" aria-label="Target project entity" value={targetEntityId} onChange={(event) => setTargetEntityId(event.target.value)}>
                {targetEntities.map((entity) => <option key={entity.id} value={entity.id}>{entityLabel(entity)}</option>)}
              </select>
            </label>
            <label className="text-xs font-medium text-slate-700">
              Link type
              <select className="input mt-1 w-full text-xs" aria-label="Cross-project link type" value={linkKind} onChange={(event) => setLinkKind(event.target.value as CrossProjectLink["link_kind"])}>
                {Object.entries(LINK_KIND_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <button className="btn btn-primary btn-sm justify-center" type="submit" disabled={busy || !sourceEntityId || !targetEntityId}>
              <Link2 size={14} className="mr-1" /> {busy ? "Saving…" : "Link entities"}
            </button>
            <label className="text-xs font-medium text-slate-700 md:col-span-2 xl:col-span-5">
              Analyst note (optional)
              <input className="input mt-1 w-full text-xs" maxLength={1200} value={rationale} onChange={(event) => setRationale(event.target.value)} placeholder="Why should an analyst compare these entities?" />
            </label>
          </form>
        ) : (
          <p className="mt-3 rounded bg-slate-50 p-3 text-xs text-slate-600">Import or compile at least one entity in each project before linking them.</p>
        )
      ) : (
        <p className="mt-3 rounded bg-slate-50 p-3 text-xs text-slate-600">Create another project before adding cross-project references.</p>
      )}

      {message && <p role="status" className="mt-3 text-xs text-indigo-700">{message}</p>}

      {links && links.length > 0 && (
        <ul className="mt-4 divide-y divide-slate-100 border-t border-slate-100">
          {links.map((link) => {
            const currentIsSource = link.from_project_id === project.id;
            const currentEntity = currentIsSource ? link.from_entity_name : link.to_entity_name;
            const otherEntity = currentIsSource ? link.to_entity_name : link.from_entity_name;
            const otherProjectId = currentIsSource ? link.to_project_id : link.from_project_id;
            const otherProjectName = currentIsSource ? link.to_project_name : link.from_project_name;
            return (
              <li key={link.id} className="flex flex-wrap items-center gap-2 py-3 text-xs">
                <span className="font-medium text-slate-800">{currentEntity}</span>
                <ArrowLeftRight size={13} className="text-slate-400" />
                <span className="text-slate-700">{otherEntity}</span>
                <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-indigo-700">{LINK_KIND_LABELS[link.link_kind]}</span>
                <button className="text-indigo-700 hover:underline" onClick={() => onSelectProject(otherProjectId)} title={`Switch to ${otherProjectName}`}>
                  <ExternalLink size={12} className="mr-1 inline" />{otherProjectName}
                </button>
                {link.rationale && <span className="basis-full pl-1 text-slate-500">{link.rationale}</span>}
                <button className="ml-auto text-slate-500 hover:text-red-700" onClick={() => void removeLink(link.id)} disabled={busy} aria-label={`Remove link between ${currentEntity} and ${otherEntity}`}>
                  <Unlink size={14} />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
