import React from "react";
import { AlertTriangle } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../../services/apiClient";

interface SourceDocument {
  sha256: string;
  title?: string;
  domain?: string;
  slop_score?: number;
  is_quarantined?: boolean;
}

export default function SlopQuarantine() {
  const { data } = useQuery({
    queryKey: ["documents"],
    queryFn: async () => {
      const resp = await apiClient.get("/ingest/documents");
      return resp.data as { documents: SourceDocument[]; count: number };
    },
  });

  const quarantined = (data?.documents ?? []).filter((doc) => doc.is_quarantined);

  return (
    <div className="p-4">
      <h3 className="font-semibold text-sm mb-2">AI Slop Quarantine Audit</h3>
      <div className="border border-red-100 bg-red-50 rounded-lg p-3 text-sm">
        <div className="flex items-center gap-2 mb-2">
          <AlertTriangle className="w-4 h-4 text-red-500" />
          <span className="font-medium text-red-800">
            {quarantined.length} quarantined document{quarantined.length === 1 ? "" : "s"}
          </span>
        </div>
        {quarantined.length > 0 && (
          <ul className="space-y-1 mt-2">
            {quarantined.map((doc) => (
              <li key={doc.sha256} className="text-xs text-red-700 truncate">
                {doc.title || doc.sha256.slice(0, 12)} (slop {doc.slop_score?.toFixed(2)})
              </li>
            ))}
          </ul>
        )}
        <p className="text-xs text-red-600 mt-2">
          Documents scoring &gt; 0.65 on the Synthetic Slop Classifier are quarantined from
          knowledge compilation.
        </p>
      </div>
    </div>
  );
}
