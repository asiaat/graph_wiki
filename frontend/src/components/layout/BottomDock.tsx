import React from "react";
import { Activity } from "lucide-react";
import AttackIndexWave from "../analytics/AttackIndexWave";

export default function BottomDock() {
  return (
    <div className="h-full flex flex-col bg-gray-100 border-t border-gray-200 overflow-hidden">
      <div className="p-2 border-b border-gray-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-gray-500" />
          <span className="text-sm font-semibold text-gray-700">
            InfoStream / Attack-Index Temporal Ribbon
          </span>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        <AttackIndexWave />
      </div>
    </div>
  );
}
