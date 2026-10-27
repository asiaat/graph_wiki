import React from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../../services/apiClient";

interface TermNode {
  term: string;
  idf_weight?: number;
  hvg_degree?: number;
  burst_score?: number;
}

interface TermEdge {
  source: string;
  target: string;
  visibility_weight?: number;
}

export default function HVGTermTree() {
  const { data, isLoading } = useQuery({
    queryKey: ["hvgTerms"],
    queryFn: async () => {
      const resp = await apiClient.get("/graph/terms");
      return resp.data as { terms: TermNode[]; edges: TermEdge[] };
    },
  });

  const terms = data?.terms ?? [];
  const edges = data?.edges ?? [];

  return (
    <div className="p-4">
      <h3 className="font-semibold text-sm mb-2">Lande Directed Term Hierarchy</h3>

      {isLoading && <p className="text-xs text-gray-500">Loading term graph...</p>}
      {!isLoading && terms.length === 0 && (
        <p className="text-xs text-gray-500">
          No term hierarchy yet - it is compiled when a document is ingested.
        </p>
      )}

      {terms.length > 0 && (
        <>
          <div className="space-y-1 mb-3">
            {terms.slice(0, 8).map((term) => (
              <div key={term.term} className="flex items-center justify-between text-xs">
                <span className="text-gray-700 truncate">{term.term}</span>
                <span className="text-gray-400 ml-2 shrink-0">deg {term.hvg_degree ?? 0}</span>
              </div>
            ))}
          </div>
          {edges.length > 0 && (
            <div className="border-t border-gray-100 pt-2 space-y-1">
              <div className="text-[10px] uppercase tracking-wide text-gray-400">
                Dominance relations
              </div>
              {edges.slice(0, 8).map((edge, index) => (
                <div key={`${edge.source}-${edge.target}-${index}`} className="text-xs text-gray-600">
                  {edge.source} <span className="text-gray-400">dominates</span> {edge.target}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
