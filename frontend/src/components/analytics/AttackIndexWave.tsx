import React from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar } from "recharts";

const mockTimeSeries = [
  { date: "Mon", attack_index: 15, doc_count: 5 },
  { date: "Tue", attack_index: 23, doc_count: 8 },
  { date: "Wed", attack_index: 45, doc_count: 12 },
  { date: "Thu", attack_index: 12, doc_count: 3 },
  { date: "Fri", attack_index: 67, doc_count: 15 },
  { date: "Sat", attack_index: 30, doc_count: 6 },
  { date: "Sun", attack_index: 18, doc_count: 4 },
];

export default function AttackIndexWave() {
  return (
    <div className="p-4">
      <h3 className="font-semibold text-sm mb-2">Attack-Index Wave</h3>
      <div className="grid grid-cols-2 gap-4 mb-4">
        <ResponsiveContainer height={200}>
          <LineChart data={mockTimeSeries}>
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip />
            <Line type="monotone" dataKey="attack_index" stroke="#ef4444" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
        <ResponsiveContainer height={200}>
          <BarChart data={mockTimeSeries}>
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip />
            <Bar dataKey="doc_count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="bg-yellow-50 border-l-4 border-yellow-500 p-3 rounded-r-lg">
        <p className="text-xs text-yellow-800">
          Wave anomaly detected on Friday: Attack-Index spiked 67 (baseline 2.3σ)
        </p>
      </div>
    </div>
  );
}