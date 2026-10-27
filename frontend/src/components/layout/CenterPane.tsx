import React, { useState } from "react";
import { FileText, Share2 } from "lucide-react";
import CompiledWikiView from "../wiki/CompiledWikiView";
import KuzuSigmaCanvas from "../graph/KuzuSigmaCanvas";
import { useEntityWiki, useSubgraph } from "../../hooks/useKuzuSubgraph";

interface CenterPaneProps {
  entityId: string | null;
}

export default function CenterPane({ entityId }: CenterPaneProps) {
  const [activeView, setActiveView] = useState<"wiki" | "graph">("wiki");

  return (
    <div className="h-full flex flex-col bg-white">
      <div className="p-4 border-b border-gray-200 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">Knowledge Workbench</h2>
        <div className="flex gap-2">
          <button
            className={`btn btn-sm ${activeView === "wiki" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setActiveView("wiki")}
          >
            <FileText size={14} className="mr-1" />
            Compiled Wiki
          </button>
          <button
            className={`btn btn-sm ${activeView === "graph" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setActiveView("graph")}
          >
            <Share2 size={14} className="mr-1" />
            Graph Canvas
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {activeView === "wiki" ? (
          <WikiView entityId={entityId} />
        ) : (
          <GraphView entityId={entityId} />
        )}
      </div>
    </div>
  );
}

function WikiView({ entityId }: { entityId: string | null }) {
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

  return <CompiledWikiView content={data.content} frontmatter={data.frontmatter} />;
}

function GraphView({ entityId }: { entityId: string | null }) {
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

  return <KuzuSigmaCanvas entities={data.entities} edges={data.edges} />;
}
