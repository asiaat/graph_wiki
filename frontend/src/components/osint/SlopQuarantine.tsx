import React from "react";
import { AlertTriangle } from "lucide-react";

export default function SlopQuarantine() {
  return (
    <div className="p-4">
      <h3 className="font-semibold text-sm mb-2">AI Slop Quarantine Audit</h3>
      <div className="border border-red-100 bg-red-50 rounded-lg p-3 text-sm">
        <div className="flex items-center gap-2 mb-2">
          <AlertTriangle className="w-4 h-4 text-red-500" />
          <span className="font-medium text-red-800">0 quarantined documents</span>
        </div>
        <p className="text-xs text-red-600">
          Documents scoring > 0.65 on the Synthetic Slop Classifier are quarantined from knowledge compilation.
        </p>
      </div>
    </div>
  );
}