import React from "react";
import { Activity, Database, FileText, ShieldAlert, Clock, Bot, TrendingUp } from "lucide-react";
import AttackIndexWave from "../analytics/AttackIndexWave";
import GraphOverviewChart from "../analytics/GraphOverviewChart";
import FullscreenFrame from "./FullscreenFrame";
import { useQuery } from "@tanstack/react-query";
import { statsApi } from "../../services/apiClient";

interface StatTileProps {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  accent?: "blue" | "green" | "yellow" | "red" | "purple";
}

function StatTile({ icon, label, value, accent = "blue" }: StatTileProps) {
  const accentColors: Record<string, string> = {
    blue: "text-blue-600",
    green: "text-green-600",
    yellow: "text-yellow-600",
    red: "text-red-600",
    purple: "text-purple-600",
  };
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 bg-white rounded border border-gray-200">
      <span className={accentColors[accent]}>{icon}</span>
      <span className="text-xs text-gray-500">{label}</span>
      <span className="text-xs font-semibold text-gray-900">{value}</span>
    </div>
  );
}

export default function BottomDock() {
  const { data: statsData } = useQuery({
    queryKey: ["stats", "dashboard"],
    queryFn: async () => {
      const resp = await statsApi.dashboard();
      return resp.data;
    },
    staleTime: 30000,
    refetchInterval: 30000,
  });

  const stats = statsData ?? {
    entities: { total: 0 },
    claims: { total: 0, evidenced: 0 },
    sources: { total: 0 },
    relations: { relates_to: 0, reprints: 0 },
    osint: { open_tickets: 0 },
    contradictions: { count: 0 },
    quality_metrics: { extraction_success_rate: 0, average_nli_score: 0 },
  };

  return (
    <div className="h-full flex flex-col bg-gray-100 border-t border-gray-200 overflow-hidden">
      <div className="p-2 border-b border-gray-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-gray-500" />
          <span className="text-sm font-semibold text-gray-700">
            InfoStream / Attack-Index Temporal Ribbon
          </span>
        </div>
        <div className="flex items-center gap-2">
          <StatTile icon={<Database size={14} />} label="Entities" value={stats.entities?.total ?? 0} accent="blue" />
          <StatTile icon={<FileText size={14} />} label="Claims" value={stats.claims?.total ?? 0} accent="green" />
          <StatTile icon={<Bot size={14} />} label="Tickets" value={stats.osint?.open_tickets ?? 0} accent="purple" />
          <StatTile icon={<ShieldAlert size={14} />} label="Contradictions" value={stats.contradictions?.count ?? 0} accent="red" />
          <StatTile icon={<TrendingUp size={14} />} label="NLI" value={`${((stats.quality_metrics?.average_nli_score ?? 0) * 100).toFixed(0)}%`} accent="yellow" />
          <StatTile icon={<Clock size={14} />} label="Last Update" value={statsData ? "live" : "offline"} accent="blue" />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        <div className="grid grid-cols-2 gap-4 p-4">
          <FullscreenFrame title="Graph Growth Overview">
            {(isFullscreen) => (
              <GraphOverviewChart
                stats={stats}
                title="Graph Growth Overview"
                height={isFullscreen ? Math.max(window.innerHeight - 120, 400) : 280}
              />
            )}
          </FullscreenFrame>
          <FullscreenFrame title="Attack-Index Wave">
            {(isFullscreen) => <AttackIndexWave expanded={isFullscreen} />}
          </FullscreenFrame>
        </div>
      </div>
    </div>
  );
}
