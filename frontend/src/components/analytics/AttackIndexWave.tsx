import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  CartesianGrid,
} from "recharts";
import { useAttackIndex } from "../../hooks/useKuzuSubgraph";

export default function AttackIndexWave() {
  const { data, isLoading, error } = useAttackIndex(30);
  const series = data?.time_series ?? [];

  return (
    <div className="p-4">
      <h3 className="font-semibold text-sm mb-2">Attack-Index Wave</h3>

      {isLoading && <p className="text-xs text-gray-500">Loading time series...</p>}
      {error && <p className="text-xs text-red-600">Could not load the Attack-Index series.</p>}
      {!isLoading && !error && series.length === 0 && (
        <p className="text-xs text-gray-500">
          No dated documents ingested yet - the ribbon fills once published sources are archived.
        </p>
      )}

      {series.length > 0 && (
        <div className="grid grid-cols-2 gap-4">
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={series}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip />
              <Line
                type="monotone"
                dataKey="avg_attack_index"
                name="Attack-Index"
                stroke="#ef4444"
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={series}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip />
              <Bar dataKey="doc_count" name="Documents" fill="#3b82f6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
