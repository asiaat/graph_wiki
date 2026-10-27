import React, { useState } from "react";
import { useComplicateEntity } from "../../hooks/useKuzuSubgraph";

interface ComplicateModalProps {
  entityId?: string | null;
  onClose: () => void;
}

export default function ComplicateModal({ entityId = null, onClose }: ComplicateModalProps) {
  const [target, setTarget] = useState(entityId ?? "");
  const complicateMutation = useComplicateEntity();

  const entityIdToUse = target.trim();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-lg w-full p-6">
        <h3 className="font-bold text-lg mb-4">Complicate Subgraph</h3>
        <p className="text-sm text-gray-600 mb-4">
          Dispatch the OSINT Complicator Agent to hunt for corroborating or refuting primary
          sources.
        </p>

        <div className="space-y-2">
          <label htmlFor="complicate-entity" className="block text-xs font-medium text-gray-700">
            Target Entity ID
          </label>
          <input
            id="complicate-entity"
            type="text"
            className="input"
            placeholder="e.g. organization:acme-corporation"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          />
        </div>

        {complicateMutation.isSuccess && (
          <div className="mt-3 bg-green-50 border-l-4 border-green-500 p-3 rounded-r-lg">
            <p className="text-xs text-green-800">
              Tickets opened:{" "}
              {((complicateMutation.data as { tickets_created?: string[] })?.tickets_created ?? []).length}
            </p>
          </div>
        )}
        {complicateMutation.error && (
          <div className="mt-3 bg-red-50 border-l-4 border-red-500 p-3 rounded-r-lg">
            <p className="text-xs text-red-800">Error: {String(complicateMutation.error)}</p>
          </div>
        )}

        <div className="flex gap-2 mt-6">
          <button className="btn btn-secondary btn-sm flex-1" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-primary btn-sm flex-1"
            disabled={!entityIdToUse || complicateMutation.isPending}
            onClick={() => {
              complicateMutation.mutate(entityIdToUse, { onSuccess: onClose });
            }}
          >
            {complicateMutation.isPending ? "Dispatching..." : "Complicate & Deepen"}
          </button>
        </div>
      </div>
    </div>
  );
}
