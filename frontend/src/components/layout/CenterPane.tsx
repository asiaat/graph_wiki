import React, { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Activity, FileText, Maximize2, Minimize2, Network, Search, Share2 } from "lucide-react";
import AttackIndexView from "../analytics/AttackIndexView";
import CompiledWikiView from "../wiki/CompiledWikiView";
import KuzuSigmaCanvas from "../graph/KuzuSigmaCanvas";
import WikiGraphView from "../graph/WikiGraphView";
import { useEntityWiki, useSubgraph } from "../../hooks/useKuzuSubgraph";
import { queryApi, wikiApi } from "../../services/apiClient";

interface QueryFinding {
  claim_id: string;
  statement: string;
  confidence: number;
  entailment: number;
  quote: string;
  source_sha256: string;
  source_title?: string | null;
  source_uri?: string | null;
  source_reliability?: string | null;
  entities: Array<{ id: string; canonical_name: string; category: string }>;
}

interface QueryResult {
  status: "ANSWERED" | "INSUFFICIENT_VERIFIED_EVIDENCE";
  answer: string;
  findings: QueryFinding[];
  gap_ticket_id?: string | null;
  filed_synthesis_id?: string | null;
}

interface CenterPaneProps {
  entityId: string | null;
  onSelectEntity: (entityId: string) => void;
}

export default function CenterPane({ entityId, onSelectEntity }: CenterPaneProps) {
  const [activeView, setActiveView] = useState<
    "wiki" | "wiki-graph" | "graph" | "query" | "attack-index"
  >(() => (window.location.hash === "#attack-index" ? "attack-index" : "wiki"));
  const [isFullscreen, setIsFullscreen] = useState(false);
  const paneRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const syncFullscreenState = () => {
      setIsFullscreen(document.fullscreenElement === paneRef.current);
    };
    const exitOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && document.fullscreenElement === paneRef.current) {
        void document.exitFullscreen();
      }
    };
    document.addEventListener("fullscreenchange", syncFullscreenState);
    document.addEventListener("keydown", exitOnEscape);
    return () => {
      document.removeEventListener("fullscreenchange", syncFullscreenState);
      document.removeEventListener("keydown", exitOnEscape);
    };
  }, []);

  useEffect(() => {
    const openAttackIndexFromHash = () => {
      if (window.location.hash === "#attack-index") setActiveView("attack-index");
    };
    window.addEventListener("hashchange", openAttackIndexFromHash);
    return () => window.removeEventListener("hashchange", openAttackIndexFromHash);
  }, []);

  function selectView(view: typeof activeView) {
    if (view !== "attack-index" && window.location.hash === "#attack-index") {
      window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
    }
    setActiveView(view);
  }

  async function toggleFullscreen() {
    if (document.fullscreenElement === paneRef.current) {
      await document.exitFullscreen();
      return;
    }
    await paneRef.current?.requestFullscreen();
  }

  async function openWikiSlug(slug: string) {
    try {
      const response = await wikiApi.getPage(slug);
      const linkedEntityId = response.data?.frontmatter?.kuzu_id;
      if (linkedEntityId) {
        onSelectEntity(String(linkedEntityId));
        setActiveView("wiki");
      }
    } catch {
      // An unavailable dossier link should not interrupt reading this page.
    }
  }

  function openEntity(entityId: string) {
    onSelectEntity(entityId);
    setActiveView("wiki");
  }

  return (
    <div ref={paneRef} className="h-full flex flex-col bg-white">
      <div className="p-4 border-b border-gray-200">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-gray-900">Knowledge Workbench</h2>
          <button
            type="button"
            className="btn btn-sm btn-secondary shrink-0"
            onClick={() => void toggleFullscreen()}
            aria-label={isFullscreen ? "Exit full screen" : "Enter full screen"}
            title={isFullscreen ? "Exit full screen (Esc)" : "Enter full screen"}
          >
            {isFullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
            <span className="ml-1">{isFullscreen ? "Exit full screen" : "Full screen"}</span>
          </button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            className={`btn btn-sm ${activeView === "wiki" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => selectView("wiki")}
          >
            <FileText size={14} className="mr-1" />
            Compiled Wiki
          </button>
          <button
            className={`btn btn-sm ${activeView === "wiki-graph" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => selectView("wiki-graph")}
          >
            <Network size={14} className="mr-1" />
            Wiki Graph
          </button>
          <button
            className={`btn btn-sm ${activeView === "graph" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => selectView("graph")}
          >
            <Share2 size={14} className="mr-1" />
            Neighborhood
          </button>
          <button
            className={`btn btn-sm ${activeView === "query" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => selectView("query")}
          >
            <Search size={14} className="mr-1" />
            Ask Graph
          </button>
          <button
            className={`btn btn-sm ${activeView === "attack-index" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => selectView("attack-index")}
          >
            <Activity size={14} className="mr-1" />
            Attack Index
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {activeView === "wiki" ? (
          <WikiView entityId={entityId} onOpenWikiSlug={openWikiSlug} />
        ) : activeView === "wiki-graph" ? (
          <WikiGraphView selectedEntityId={entityId} onOpenEntity={openEntity} />
        ) : activeView === "graph" ? (
          <GraphView entityId={entityId} onOpenEntity={openEntity} />
        ) : activeView === "attack-index" ? (
          <AttackIndexView />
        ) : (
          <QueryView entityId={entityId} />
        )}
      </div>
    </div>
  );
}

function QueryView({ entityId }: { entityId: string | null }) {
  const [question, setQuestion] = useState("");
  const [saveToWiki, setSaveToWiki] = useState(false);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (question.trim().length < 3 || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await queryApi.compiled(question.trim(), entityId, saveToWiki);
      setResult(response.data as QueryResult);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The graph query failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-4xl p-5 space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Ask the compiled graph</h1>
        <p className="mt-1 text-sm text-gray-600">
          Results include only claims with a source quote, entailment of at least 0.85,
          confidence of at least 0.70, and no unresolved contradiction.
        </p>
        {entityId && (
          <p className="mt-1 text-xs text-gray-500">Scoped to selected entity: {entityId}</p>
        )}
      </div>

      <form onSubmit={submit} className="space-y-3">
        <label className="block text-sm font-medium text-gray-700" htmlFor="graph-question">
          Question
        </label>
        <textarea
          id="graph-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="What verified relationships does the graph record?"
          maxLength={2000}
          rows={3}
          className="input w-full resize-y"
          required
          minLength={3}
        />
        <div className="flex items-center justify-between gap-4">
          <label className="flex items-center gap-2 text-xs text-gray-600">
            <input
              type="checkbox"
              checked={saveToWiki}
              onChange={(event) => setSaveToWiki(event.target.checked)}
            />
            Save supported findings as a synthesis concept
          </label>
          <button
            type="submit"
            disabled={loading || question.trim().length < 3}
            className="btn-primary btn-sm"
          >
            {loading ? "Searching evidence…" : "Search graph"}
          </button>
        </div>
      </form>

      {error && (
        <p role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {result && (
        <section aria-live="polite" className="space-y-4">
          {result.status === "INSUFFICIENT_VERIFIED_EVIDENCE" ? (
            <div className="rounded border border-amber-200 bg-amber-50 p-4">
              <h2 className="font-semibold text-amber-900">Insufficient verified evidence</h2>
              <p className="mt-1 text-sm text-amber-800">
                No matching claim met the confidence, entailment, and source requirements.
                An OSINT gap ticket was opened.
              </p>
              {result.gap_ticket_id && (
                <p className="mt-2 font-mono text-xs text-amber-800">{result.gap_ticket_id}</p>
              )}
            </div>
          ) : (
            <>
              <h2 className="font-semibold text-gray-900">Verified findings</h2>
              {result.findings.map((finding) => (
                <article key={finding.claim_id} className="rounded border border-gray-200 bg-white p-4 space-y-3">
                  <p className="font-medium text-gray-900">{finding.statement}</p>
                  <blockquote className="border-l-2 border-blue-300 pl-3 text-sm text-gray-700">
                    “{finding.quote}”
                  </blockquote>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
                    <span>Confidence {(finding.confidence * 100).toFixed(0)}%</span>
                    <span>Entailment {(finding.entailment * 100).toFixed(0)}%</span>
                    {finding.source_reliability && <span>Source {finding.source_reliability}</span>}
                  </div>
                  <p className="break-all text-xs text-gray-500">
                    {finding.source_title || finding.source_uri || "Source document"} · SHA-256{" "}
                    {finding.source_sha256}
                  </p>
                </article>
              ))}
              {result.filed_synthesis_id && (
                <p className="text-xs text-green-700">Saved as {result.filed_synthesis_id}</p>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}

function WikiView({
  entityId,
  onOpenWikiSlug,
}: {
  entityId: string | null;
  onOpenWikiSlug: (slug: string) => void;
}) {
  const { data, isLoading, error } = useEntityWiki(entityId ?? "");

  if (!entityId) {
    return (
      <div className="p-4 prose max-w-none">
        <h1>Welcome to Compiled Wiki</h1>
        <p className="text-gray-600">
          Select an entity to view its compiled markdown dossier with verbatim source citations.
        </p>
        <div className="mt-8 rounded-lg border border-gray-200 bg-gray-50 p-8 text-center">
          <p className="text-gray-500">No entity selected yet.</p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return <p className="p-4 text-sm text-gray-500">Loading dossier...</p>;
  }
  if (error) {
    return <p className="p-4 text-sm text-red-600">Could not load dossier: {String(error)}</p>;
  }
  if (!data) {
    return <p className="p-4 text-sm text-gray-500">No dossier compiled for this entity.</p>;
  }

  return (
    <CompiledWikiView
      content={data.content}
      frontmatter={data.frontmatter}
      onOpenWikiSlug={onOpenWikiSlug}
    />
  );
}

function GraphView({
  entityId,
  onOpenEntity,
}: {
  entityId: string | null;
  onOpenEntity: (entityId: string) => void;
}) {
  const { data, isLoading, error } = useSubgraph(entityId ?? "");

  if (!entityId) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-gray-500">Select an entity to render its neighbourhood.</div>
      </div>
    );
  }
  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-gray-500">Loading subgraph...</div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-red-600">Could not load subgraph: {String(error)}</div>
      </div>
    );
  }
  if (!data || data.entities.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-gray-500">No relations recorded for this entity yet.</div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-slate-200 bg-white px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-900">Neighborhood around {data.entities.find((entity) => entity.id === entityId)?.canonical_name ?? "selected entity"}</h3>
        <p className="mt-1 text-xs text-slate-600">A neighborhood is the local network of entities connected to the selected entity.</p>
        <details className="mt-2 max-w-3xl rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-700">
          <summary className="cursor-pointer font-medium text-slate-800">How should I read this neighborhood?</summary>
          <div className="mt-2 space-y-1.5 leading-5">
            <p>The view follows recorded relations up to two steps away by default, in either direction. Each step is one relation edge; the arrows still show the recorded source-to-target direction.</p>
            <p>Entities farther from the selected one are connected indirectly. Their presence in this view does not by itself prove a direct relationship or a causal link.</p>
            <p>Only compiled entities and relations currently returned by the graph are shown. Missing links can mean they have not been recorded or verified.</p>
          </div>
        </details>
      </div>
      <div className="min-h-0 flex-1">
        <KuzuSigmaCanvas
          entities={data.entities}
          edges={data.edges}
          rootId={entityId}
          onOpenEntity={onOpenEntity}
        />
      </div>
    </div>
  );
}
