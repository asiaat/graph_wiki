import React from "react";
import { ShieldAlert, Clock } from "lucide-react";
import SwarmMentorQueue from "../osint/SwarmMentorQueue";
import SlopQuarantine from "../osint/SlopQuarantine";
import HVGTermTree from "../graph/HVGTermTree";
import { useContradictions } from "../../hooks/useKuzuSubgraph";

interface RightPaneProps {
  entityId: string | null;
}

export default function RightPane({ entityId }: RightPaneProps) {
  const { data } = useContradictions();
  const contradictions = data?.contradictions ?? [];
  const waveAlerts = data?.wave_alerts ?? [];

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
            <div className="min-w-0">
              <h3 className="font-semibold text-sm">Contradiction Alerts</h3>
              {contradictions.length === 0 ? (
                <p className="text-xs text-gray-500 mt-1">
                  No opposing claims detected in the compiled graph.
                </p>
              ) : (
                <ul className="mt-2 space-y-2">
                  {contradictions.map((alert, index) => (
                    <li key={`${alert.claim_a}-${alert.claim_b}-${index}`} className="text-xs">
                      <div className="font-medium text-gray-800">{alert.entity_name}</div>
                      <div className="text-gray-600 truncate">{alert.statement_a}</div>
                      <div className="text-gray-600 truncate">{alert.statement_b}</div>
                      <div className="text-red-500 mt-0.5">
                        severity {typeof alert.severity === "number" ? alert.severity.toFixed(2) : "?"}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-start gap-3">
            <Clock className="w-5 h-5 text-orange-600 mt-0.5" />
            <div className="min-w-0">
              <h3 className="font-semibold text-sm">Attack-Index Wave Anomalies</h3>
              {waveAlerts.length === 0 ? (
                <p className="text-xs text-gray-500 mt-1">No wave exceeded 2.5σ.</p>
              ) : (
                <ul className="mt-2 space-y-1">
                  {waveAlerts.map((alert, index) => (
                    <li key={index} className="text-xs text-gray-700 flex justify-between">
                      <span className="truncate">{alert.term ?? "unknown term"}</span>
                      <span className="text-orange-600">z {alert.z_score.toFixed(2)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>

        <div className="card">
          <h3 className="font-semibold text-sm mb-2">Admiralty Scale</h3>
          <div className="flex flex-wrap gap-2">
            <span className="badge badge-admiralty-a">A</span>
            <span className="badge badge-admiralty-b">B</span>
            <span className="badge badge-admiralty-c">C</span>
            <span className="badge badge-admiralty-d">D</span>
            <span className="badge badge-admiralty-e">E</span>
            <span className="badge badge-admiralty-f">F</span>
          </div>
        </div>

        <HVGTermTree />
        <SlopQuarantine />
        <SwarmMentorQueue entityId={entityId} />
      </div>
    </div>
  );
}
