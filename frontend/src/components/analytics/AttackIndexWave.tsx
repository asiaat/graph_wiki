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

interface AttackIndexWaveProps {
  expanded?: boolean;
}

export default function AttackIndexWave({ expanded = false }: AttackIndexWaveProps) {
  const { data, isLoading, error } = useAttackIndex(30);
  const series = data?.time_series ?? [];
  const chartHeight = expanded ? Math.max(window.innerHeight - 170, 400) : 180;

  return (
    <div className={expanded ? "p-6" : "p-4"}>
      <h3 className={expanded ? "mb-2 text-xl font-semibold" : "mb-2 text-sm font-semibold"}>
        Attack-Index Wave
      </h3>

      {isLoading && <p className="text-xs text-gray-500">Loading time series...</p>}
      {error && <p className="text-xs text-red-600">Could not load the Attack-Index series.</p>}
      {!isLoading && !error && series.length === 0 && (
        <p className="text-xs text-gray-500">
          No dated documents ingested yet - the ribbon fills once published sources are archived.
        </p>
      )}

      {series.length > 0 && (
        <div className={`grid grid-cols-1 gap-5 ${expanded ? "xl:grid-cols-2" : "grid-cols-2"}`}>
          <ResponsiveContainer width="100%" height={chartHeight}>
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
          <ResponsiveContainer width="100%" height={chartHeight}>
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
