import React from "react";

export default function HVGTermTree() {
  return (
    <div className="p-4">
      <h3 className="font-semibold text-sm mb-2">Lande Directed Term Hierarchy</h3>
      <div className="space-y-2 text-sm">
        <div className="flex items-center gap-2 text-gray-700">
          <span className="text-xs text-gray-400">→</span>
          <span>UAV (hub term)</span>
        </div>
        <div className="ml-4 flex items-center gap-2 text-gray-600">
          <span className="text-xs text-gray-400">→</span>
          <span>Propulsion System</span>
        </div>
        <div className="ml-8 flex items-center gap-2 text-gray-500">
          <span className="text-xs text-gray-400">→</span>
          <span>Electric Motor</span>
        </div>
      </div>
    </div>
  );
}