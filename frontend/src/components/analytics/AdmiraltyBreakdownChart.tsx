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

const ADMIRALTY_ORDER: Record<string, number> = {
  A_COMPLETELY_RELIABLE: 0,
  B_USUALLY_RELIABLE: 1,
  C_FAIRLY_RELIABLE: 2,
  D_NOT_USUALLY_RELIABLE: 3,
  E_UNRELIABLE: 4,
  F_CANNOT_BE_JUDGED: 5,
};

const ADMIRALTY_LABELS: Record<string, string> = {
  A_COMPLETELY_RELIABLE: "A - Completely Reliable",
  B_USUALLY_RELIABLE: "B - Usually Reliable",
  C_FAIRLY_RELIABLE: "C - Fairly Reliable",
  D_NOT_USUALLY_RELIABLE: "D - Not Usually Reliable",
  E_UNRELIABLE: "E - Unreliable",
  F_CANNOT_BE_JUDGED: "F - Cannot Be Judged",
};

interface AdmiraltyBreakdownChartProps {
  data: Record<string, number>;
  title?: string;
  height?: number;
}

export default function AdmiraltyBreakdownChart({
  data,
  title = "Source Admiralty Ratings",
  height = 220,
}: AdmiraltyBreakdownChartProps) {
  const entries = Object.entries(data)
    .sort((a, b) => ADMIRALTY_ORDER[a[0] ?? ""] - ADMIRALTY_ORDER[b[0] ?? ""])
    .filter(([, v]) => v > 0);

  const maxValue = entries.length > 0 ? Math.max(...entries.map(([, v]) => v)) : 1;

  if (entries.length === 0) {
    return (
      <div className="p-4">
        <h3 className="font-semibold text-sm mb-2">{title}</h3>
        <p className="text-xs text-gray-500">No source reliability ratings yet.</p>
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
          <YAxis type="category" dataKey="0" tick={{ fontSize: 10 }} width={140} />
          <Tooltip
            formatter={(value) => [value ?? 0, "Sources"]}
            contentStyle={{ backgroundColor: "#fff", border: "1px solid #e5e7eb", borderRadius: "4px" }}
          />
          <Bar dataKey="1" name="Sources" fill="#ef4444" radius={[0, 4, 4, 0]} maxBarSize={24} />
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-3 flex flex-wrap gap-2 justify-center">
        {entries.map(([rating]) => (
          <span key={rating} className="inline-block px-2 py-0.5 rounded text-[10px] font-medium text-gray-900 bg-gray-100 border border-gray-200">
            {ADMIRALTY_LABELS[rating] ?? rating}
          </span>
        ))}
      </div>
    </div>
  );
}
