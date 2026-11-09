import React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

interface EntityCategoryChartProps {
  data: Record<string, number>;
  title?: string;
  height?: number;
}

export default function EntityCategoryChart({
  data,
  title = "Entities by Category",
  height = 220,
}: EntityCategoryChartProps) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const maxValue = entries.length > 0 ? Math.max(...entries.map(([, v]) => v)) : 1;

  if (entries.length === 0) {
    return (
      <div className="p-4">
        <h3 className="font-semibold text-sm mb-2">{title}</h3>
        <p className="text-xs text-gray-500">No entity categories yet.</p>
      </div>
    );
  }

  return (
    <div className="p-4">
      <h3 className="font-semibold text-sm mb-2">{title}</h3>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={entries} layout="vertical" margin={{ left: 10, right: 10, top: 10, bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis type="number" tick={{ fontSize: 10 }} domain={[0, maxValue * 1.2]} />
          <YAxis type="category" dataKey="0" tick={{ fontSize: 10 }} width={110} />
          <Tooltip
            formatter={(value) => [value ?? 0, "Entities"]}
            contentStyle={{ backgroundColor: "#fff", border: "1px solid #e5e7eb", borderRadius: "4px" }}
          />
          <Bar
            dataKey="1"
            name="Count"
            fill="#3b82f6"
            radius={[0, 4, 4, 0]}
            maxBarSize={24}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
