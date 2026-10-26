import React from "react";
import { ShieldAlert, Clock } from "lucide-react";

export default function RightPane() {
  return (
    <div className="h-full flex flex-col bg-white border-l border-gray-200 overflow-hidden">
      <div className="p-4 border-b border-gray-200">
        <h2 className="text-lg font-semibold text-gray-900">JEV Verification Inspector</h2>
        <p className="text-xs text-gray-500 mt-1">Mentor Console / Contradiction Alerts</p>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div className="card">
          <div className="flex items-start gap-3">
            <ShieldAlert className="w-5 h-5 text-blue-600 mt-0.5" />
            <div>
              <h3 className="font-semibold text-sm">Verbatim Gate Status</h3>
              <p className="text-xs text-gray-500">All claims verified against source span</p>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-start gap-3">
            <Clock className="w-5 h-5 text-orange-600 mt-0.5" />
            <div>
              <h3 className="font-semibold text-sm">Admiralty Ratings</h3>
              <div className="flex gap-2 mt-2">
                <span className="badge badge-admiralty-a">A - COMPLETELY_RELIABLE</span>
                <span className="badge badge-admiralty-b">B - USUALLY_RELIABLE</span>
                <span className="badge badge-admiralty-c">C - FAIRLY_RELIABLE</span>
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-start gap-3">
            <ShieldAlert className="w-5 h-5 text-red-600 mt-0.5" />
            <div>
              <h3 className="font-semibold text-sm">Contradiction Alerts</h3>
              <p className="text-xs text-gray-500">Review pending human adjudication</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}