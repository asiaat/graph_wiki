import React, { useState } from "react";
import { Search, TrendingUp, AlertTriangle } from "lucide-react";
import { useComplicateEntity } from "../../hooks/useKuzuSubgraph";

export default function SwarmMentorQueue() {
  const [entityId, setEntityId] = useState("");
  const complicateMutation = useComplicateEntity();

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center gap-2">
        <Search size={20} className="text-gray-500" />
        <h3 className="font-semibold text-sm">Complicate Subgraph</h3>
      </div>
      <div className="space-y-2">
        <div className="relative">
          <input
            type="text"
            placeholder="Enter entity ID (e.g., org:geran-uav-plant-alabuga)"
            value={entityId}
            onChange={(e) => setEntityId(e.target.value)}
            className="input pl-10"
          />
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 h-4 w-4" />
        </div>
        <button
          disabled={!entityId || complicateMutation.isPending}
          onClick={() => complicateMutation.mutate(entityId)}
          className="btn-primary btn-sm w-full"
        >
          {complicateMutation.isPending ? "Complicating..." : "Dispatch OSINT Agent"}
        </button>
      </div>
      {complicateMutation.isPending && (
        <div className="bg-yellow-50 border-l-4 border-yellow-500 p-3 rounded-r-lg">
          <p className="text-xs text-yellow-800">OSINT agent hunting for corroborating sources...</p>
        </div>
      )}
      {complicateMutation.error && (
        <div className="bg-red-50 border-l-4 border-red-500 p-3 rounded-r-lg">
          <p className="text-xs text-red-800">Error: {complicateMutation.error}</p>
        </div>
      )}
    </div>
  );
}