import React from "react";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

const CONFIDENCE_COLORS = {
  high: "#22c55e",
  medium: "#eab308",
  low: "#ef4444",
};

const CONFIDENCE_LABELS: Record<string, string> = {
  high: "High (≥0.8)",
  medium: "Medium (0.5–0.8)",
  low: "Low (<0.5)",
};

interface ClaimConfidenceChartProps {
  data: { high: number; medium: number; low: number };
  title?: string;
  height?: number;
}

export default function ClaimConfidenceChart({
  data,
  title = "Claim Confidence Distribution",
  height = 220,
}: ClaimConfidenceChartProps) {
  const entries = [
    { name: "high", value: data.high ?? 0, label: CONFIDENCE_LABELS.high },
    { name: "medium", value: data.medium ?? 0, label: CONFIDENCE_LABELS.medium },
    { name: "low", value: data.low ?? 0, label: CONFIDENCE_LABELS.low },
  ].filter((e) => e.value > 0);

  const total = entries.reduce((sum, e) => sum + e.value, 0);

  if (total === 0) {
    return (
      <div className="p-4">
        <h3 className="font-semibold text-sm mb-2">{title}</h3>
        <p className="text-xs text-gray-500">No claims with confidence scores yet.</p>
      </div>
    );
  }

  return (
    <div className="p-4">
      <h3 className="font-semibold text-sm mb-2">{title}</h3>
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie
            data={entries}
            cx="50%"
            cy="50%"
            innerRadius={50}
            outerRadius={90}
            paddingAngle={2}
            dataKey="value"
            nameKey="name"
            label={({ value, percent }) => `${value} (${((percent ?? 0) * 100).toFixed(0)}%)`}
            labelLine={false}
          >
            {entries.map((entry) => (
              <Cell
                key={`cell-${entry.name}`}
                fill={CONFIDENCE_COLORS[entry.name as keyof typeof CONFIDENCE_COLORS] ?? "#9ca3af"}
              />
            ))}
          </Pie>
          <Tooltip
            formatter={(value, name) => [value ?? 0, CONFIDENCE_LABELS[String(name)] ?? String(name)]}
            contentStyle={{ backgroundColor: "#fff", border: "1px solid #e5e7eb", borderRadius: "4px" }}
          />
          <Legend
            layout="vertical"
            align="left"
            verticalAlign="bottom"
            wrapperStyle={{ paddingTop: 20 }}
            formatter={(value: string) => CONFIDENCE_LABELS[value] ?? value}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
