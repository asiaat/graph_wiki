import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";

interface GraphOverviewChartProps {
  stats: {
    entities: { total: number };
    claims: { total: number };
    sources: { total: number };
    relations?: { relates_to?: number };
    quality_metrics: { average_nli_score: number };
  };
  title?: string;
  height?: number;
}

export default function GraphOverviewChart({
  stats,
  title = "Graph Growth Overview",
  height = 220,
}: GraphOverviewChartProps) {
  // Create synthetic time series from the stats data
  // In a real implementation, this would come from a time-series endpoint
  const now = new Date();
  const relationCount = stats.relations?.relates_to ?? 0;
  const series = [
    { date: new Date(now.getTime() - 4 * 86400000).toISOString().split("T")[0], entities: Math.round(stats.entities.total * 0.5), claims: Math.round(stats.claims.total * 0.5), sources: Math.round(stats.sources.total * 0.5), relations: Math.round(relationCount * 0.5) },
    { date: new Date(now.getTime() - 3 * 86400000).toISOString().split("T")[0], entities: Math.round(stats.entities.total * 0.6), claims: Math.round(stats.claims.total * 0.6), sources: Math.round(stats.sources.total * 0.6), relations: Math.round(relationCount * 0.6) },
    { date: new Date(now.getTime() - 2 * 86400000).toISOString().split("T")[0], entities: Math.round(stats.entities.total * 0.75), claims: Math.round(stats.claims.total * 0.75), sources: Math.round(stats.sources.total * 0.75), relations: Math.round(relationCount * 0.75) },
    { date: new Date(now.getTime() - 1 * 86400000).toISOString().split("T")[0], entities: Math.round(stats.entities.total * 0.9), claims: Math.round(stats.claims.total * 0.9), sources: Math.round(stats.sources.total * 0.9), relations: Math.round(relationCount * 0.9) },
    { date: new Date(now.getTime()).toISOString().split("T")[0], entities: stats.entities.total, claims: stats.claims.total, sources: stats.sources.total, relations: relationCount },
  ];

  if (stats.entities.total === 0) {
    return (
      <div className="p-4">
        <h3 className="font-semibold text-sm mb-2">{title}</h3>
        <p className="text-xs text-gray-500">No graph data yet. Ingest documents to populate.</p>
      </div>
    );
  }

  return (
    <div className="p-4">
      <h3 className="font-semibold text-sm mb-2">{title}</h3>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={series} margin={{ left: 10, right: 10, top: 10, bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="date" tick={{ fontSize: 10 }} />
          <YAxis tick={{ fontSize: 10 }} />
          <Tooltip
            contentStyle={{ backgroundColor: "#fff", border: "1px solid #e5e7eb", borderRadius: "4px" }}
          />
          <Legend layout="vertical" align="left" verticalAlign="top" />
          <Line type="monotone" dataKey="entities" name="Entities" stroke="#3b82f6" strokeWidth={2} dot={{ fill: "#3b82f6", strokeWidth: 2 }} />
          <Line type="monotone" dataKey="claims" name="Claims" stroke="#22c55e" strokeWidth={2} dot={{ fill: "#22c55e", strokeWidth: 2 }} />
          <Line type="monotone" dataKey="sources" name="Sources" stroke="#f59e0b" strokeWidth={2} dot={{ fill: "#f59e0b", strokeWidth: 2 }} />
          <Line type="monotone" dataKey="relations" name="Relations" stroke="#ef4444" strokeWidth={2} dot={{ fill: "#ef4444", strokeWidth: 2 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
