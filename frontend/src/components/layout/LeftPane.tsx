import React from "react";
import { Database, FileText, Bot } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../../services/apiClient";

export default function LeftPane() {
  const { data: entities } = useQuery({
    queryKey: ["entities", "count"],
    queryFn: async () => {
      const resp = await apiClient.get("/graph/entities/count");
      return resp.data;
    },
  });

  const { data: docs } = useQuery({
    queryKey: ["docs", "count"],
    queryFn: async () => {
      const resp = await apiClient.get("/ingest/documents");
      return resp.data;
    },
  });

  return (
    <div className="h-full flex flex-col bg-white border-r border-gray-200 overflow-hidden">
      <div className="p-4 border-b border-gray-200">
        <h2 className="text-lg font-semibold text-gray-900">Knowledge Workspace</h2>
        <p className="text-xs text-gray-500 mt-1">Ontology Tree / Source Vault / Agent Queue</p>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        <div className="space-y-4">
          <div className="card">
            <div className="flex items-center gap-2 mb-2">
              <Database size={16} />
              <span className="font-semibold text-sm">KùzuDB Entities</span>
            </div>
            <div className="text-2xl font-bold text-blue-600">{entities?.total || 0}</div>
            <p className="text-xs text-gray-500 mt-1">Compiled entity nodes</p>
          </div>

          <div className="card">
            <div className="flex items-center gap-2 mb-2">
              <FileText size={16} />
              <span className="font-semibold text-sm">Source Documents</span>
            </div>
            <div className="text-2xl font-bold text-blue-600">{docs?.count || 0}</div>
            <p className="text-xs text-gray-500 mt-1">Archived in raw vault</p>
          </div>

          <div className="card">
            <div className="flex items-center gap-2 mb-2">
              <Bot size={16} />
              <span className="font-semibold text-sm">Agent Queue</span>
            </div>
            <div className="space-y-2">
              <div className="text-xs text-gray-700">Gatekeeper & Anti-Slop</div>
              <div className="text-xs text-gray-700">Lande HVG Network</div>
              <div className="text-xs text-gray-700">JEV Swarm (3 experts)</div>
              <div className="text-xs text-gray-700">Graph Wiki Compiler</div>
              <div className="text-xs text-gray-700">Adversarial Linter</div>
              <div className="text-xs text-gray-700">OSINT Complicator</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}