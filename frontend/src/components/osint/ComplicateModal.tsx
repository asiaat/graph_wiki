import React from "react";

export default function ComplicateModal() {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-lg w-full p-6">
        <h3 className="font-bold text-lg mb-4">Complicate Subgraph</h3>
        <p className="text-sm text-gray-600 mb-4">
          Dispatch the OSINT Complicator Agent to hunt for corroborating or refuting primary sources.
        </p>
        <div className="space-y-2">
          <label className="block text-xs font-medium text-gray-700">Target Entity ID</label>
          <input type="text" className="input" placeholder="e.g., org:geran-uav-plant-alabuga" />
        </div>
        <div className="flex gap-2 mt-6">
          <button className="btn btn-secondary btn-sm flex-1">Cancel</button>
          <button className="btn-primary btn-sm flex-1">Complicate & Deepen</button>
        </div>
      </div>
    </div>
  );
}