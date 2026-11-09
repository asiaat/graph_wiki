import React from "react";
import { ShieldAlert, Clock, Database, Bot, PieChart } from "lucide-react";
import SwarmMentorQueue from "../osint/SwarmMentorQueue";
import SlopQuarantine from "../osint/SlopQuarantine";
import HVGTermTree from "../graph/HVGTermTree";
import { useContradictions } from "../../hooks/useKuzuSubgraph";
import { useQuery } from "@tanstack/react-query";
import { statsApi } from "../../services/apiClient";
import type { DashboardStats } from "../../types/jevGraph";
import EntityCategoryChart from "../analytics/EntityCategoryChart";
import AdmiraltyBreakdownChart from "../analytics/AdmiraltyBreakdownChart";
import ClaimConfidenceChart from "../analytics/ClaimConfidenceChart";
import FullscreenFrame from "./FullscreenFrame";

interface RightPaneProps {
  entityId: string | null;
}

interface StatCardProps {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}

function StatCard({ icon, title, children }: StatCardProps) {
  return (
    <div className="card">
      <div className="flex items-start gap-3">
        <div className="mt-0.5">{icon}</div>
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-sm">{title}</h3>
          {children}
        </div>
      </div>
    </div>
  );
}

export default function RightPane({ entityId }: RightPaneProps) {
  const { data: contradictionsData } = useContradictions();
  const contradictions = contradictionsData?.contradictions ?? [];
  const waveAlerts = contradictionsData?.wave_alerts ?? [];

  const { data: statsData, isLoading: statsLoading } = useQuery<DashboardStats>({
    queryKey: ["stats", "dashboard"],
    queryFn: async () => {
      const resp = await statsApi.dashboard();
      return resp.data as DashboardStats;
    },
    staleTime: 30000,
    refetchInterval: 30000,
  });

  const stats = statsData ?? {
    sources: { total: 0, admiralty_breakdown: {}, quarantined: 0 },
    entities: { total: 0, by_category: {} },
    claims: { total: 0, evidenced: 0, confidence_distribution: { high: 0, medium: 0, low: 0 } },
    relations: { relates_to: 0, reprints: 0 },
    contradictions: { count: 0 },
    osint: { open_tickets: 0, synth_concepts: 0 },
    quality_metrics: { extraction_success_rate: 0, average_nli_score: 0, total_claims_with_nli: 0 },
    activity: { recent_ingestions: [], last_update: null },
  };

  const admiralty = stats.sources?.admiralty_breakdown ?? {};
  const entityCategories = stats.entities?.by_category ?? {};
  const confDist = stats.claims?.confidence_distribution ?? { high: 0, medium: 0, low: 0 };
  const quality = stats.quality_metrics ?? { extraction_success_rate: 0, average_nli_score: 0 };

  return (
    <div className="h-full flex flex-col bg-white border-l border-gray-200 overflow-hidden">
      <div className="p-4 border-b border-gray-200">
        <h2 className="text-lg font-semibold text-gray-900">JEV Verification Inspector</h2>
        <p className="text-xs text-gray-500 mt-1">Mentor Console / Contradiction Alerts</p>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">

        {/* ─── Overview Ribbon ─── */}
        <StatCard icon={<Database className="w-5 h-5 text-blue-600" />} title="Graph Statistics">
          <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
            <div className="flex justify-between">
              <span className="text-gray-600">Entities</span>
              <span className="font-medium text-gray-900">{stats.entities?.total ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Claims</span>
              <span className="font-medium text-gray-900">{stats.claims?.total ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Evidenced Claims</span>
              <span className="font-medium text-green-600">{stats.claims?.evidenced ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Relations</span>
              <span className="font-medium text-gray-900">{stats.relations?.relates_to ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Sources</span>
              <span className="font-medium text-gray-900">{stats.sources?.total ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Contradictions</span>
              <span className="font-medium text-red-600">{stats.contradictions?.count ?? 0}</span>
            </div>
          </div>
        </StatCard>

        {/* ─── OSINT Tickets ─── */}
        <StatCard icon={<Bot className="w-5 h-5 text-purple-600" />} title="OSINT Activity">
          <div className="mt-2 space-y-1 text-xs">
            <div className="flex justify-between">
              <span className="text-gray-600">Open Tickets</span>
              <span className="font-medium text-orange-600">{stats.osint?.open_tickets ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Synthesis Concepts</span>
              <span className="font-medium text-indigo-600">{stats.osint?.synth_concepts ?? 0}</span>
            </div>
          </div>
        </StatCard>

        {/* ─── Entity Category Chart ─── */}
        <FullscreenFrame title="Entities by Category">
          {(isFullscreen) => statsLoading ? (
            <div className="p-4">
              <h3 className="font-semibold text-sm mb-2">Entities by Category</h3>
              <p className="text-xs text-gray-500">Loading categories...</p>
            </div>
          ) : Object.keys(entityCategories).length > 0 ? (
            <EntityCategoryChart
              data={entityCategories}
              title="Entities by Category"
              height={isFullscreen ? Math.max(window.innerHeight - 120, 400) : 220}
            />
          ) : (
            <div className="p-4">
              <h3 className="font-semibold text-sm mb-2">Entities by Category</h3>
              <p className="text-xs text-gray-500">No entity categories yet.</p>
            </div>
          )}
        </FullscreenFrame>

        {/* ─── Admiralty Breakdown Chart ─── */}
        <FullscreenFrame title="Source Admiralty Ratings">
          {(isFullscreen) => (
            <AdmiraltyBreakdownChart
              data={admiralty}
              title="Source Admiralty Ratings"
              height={isFullscreen ? Math.max(window.innerHeight - 120, 400) : 220}
            />
          )}
        </FullscreenFrame>

        {/* ─── Confidence Chart ─── */}
        <FullscreenFrame title="Claim Confidence">
          {(isFullscreen) => (
            <ClaimConfidenceChart
              data={confDist}
              title="Claim Confidence"
              height={isFullscreen ? Math.max(window.innerHeight - 120, 400) : 220}
            />
          )}
        </FullscreenFrame>

        {/* ─── Quality Metrics ─── */}
        <StatCard icon={<PieChart className="w-5 h-5 text-cyan-600" />} title="JEV Quality Metrics">
          <div className="mt-2 space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="text-gray-600">Extraction Success Rate</span>
              <span className="font-medium text-cyan-600">{(quality?.extraction_success_rate * 100).toFixed(1)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Avg NLI Entailment</span>
              <span className="font-medium text-cyan-600">
                {(quality?.average_nli_score * 100).toFixed(1)}%
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Claims with NLI scores</span>
              <span className="font-medium text-gray-900">
                {quality?.total_claims_with_nli ?? 0}
              </span>
            </div>
          </div>
        </StatCard>

        {/* ─── Contradiction Alerts ─── */}
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

        {/* ─── Attack-Index Wave Anomalies ─── */}
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

        {/* ─── Admiralty Scale Reference ─── */}
        <div className="card">
          <h3 className="font-semibold text-sm mb-2">Admiralty Scale Reference</h3>
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
