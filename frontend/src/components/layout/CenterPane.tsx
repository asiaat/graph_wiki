import React, { useState } from "react";
import { FileText, Share2 } from "lucide-react";

export default function CenterPane() {
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
        {activeView === "wiki" ? <WikiView /> : <GraphView />}
      </div>
    </div>
  );
}

function WikiView() {
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

function GraphView() {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-gray-500">Graph canvas would render here (Sigma.js/Cosmograph).</div>
    </div>
  );
}