import { Activity, FileJson, FileText } from "lucide-react";
import type { ReactNode } from "react";
import AttackIndexWave from "./AttackIndexWave";
import { useAttackIndex } from "../../hooks/useKuzuSubgraph";

export default function AttackIndexView() {
  const { data } = useAttackIndex(30);
  const latest = data?.time_series[data.time_series.length - 1];
  const average = latest?.avg_attack_index;
  const documents = latest?.doc_count;

  return (
    <main className="mx-auto w-full max-w-6xl p-5 md:p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-purple-700">
            <Activity size={20} />
            <span className="text-xs font-semibold uppercase tracking-wide">Narrative activity</span>
          </div>
          <h1 className="mt-2 text-2xl font-bold text-slate-900">Attack-Index overview</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            The charts show daily average Attack-Index scores and the number of dated source documents in the last 30 days.
          </p>
          <details className="mt-3 max-w-3xl rounded-md bg-purple-50 px-3 py-2 text-xs text-slate-700">
            <summary className="cursor-pointer font-medium text-slate-800">What does the Attack Index mean?</summary>
            <div className="mt-2 space-y-1.5 leading-5">
              <p>It is a screening signal for changes in language patterns across ingested documents, not a finding that an information attack occurred.</p>
              <p>In the current pipeline, the saved score is a capped burstiness proxy: burstiness divided by 25, up to 1. The chart averages available document scores by publication day and shows the document count.</p>
              <p>The linter can flag unusually high scores against a seven-day baseline (above 2.5 standard deviations when there are enough samples). Treat a spike as a prompt for source review; it does not establish coordination, intent, or truth.</p>
            </div>
          </details>
        </div>
        <a
          className="btn btn-secondary btn-sm"
          href={`/api/v1/osint/attack-index?days=30&project_id=${encodeURIComponent(window.localStorage.getItem("kuzuwiki.projectId") || "default")}`}
          target="_blank"
          rel="noopener noreferrer"
        >
          <FileJson size={14} className="mr-1" />
          Raw JSON
        </a>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <MetricCard
          icon={<Activity size={16} />}
          label="Latest daily average"
          value={typeof average === "number" ? average.toFixed(2) : "No data"}
        />
        <MetricCard
          icon={<FileText size={16} />}
          label="Dated documents on latest day"
          value={typeof documents === "number" ? documents : "No data"}
        />
      </div>

      <section className="mt-6 rounded-xl border border-slate-200 bg-white shadow-sm">
        <AttackIndexWave expanded />
      </section>
    </main>
  );
}

function MetricCard({ icon, label, value }: { icon: ReactNode; label: string; value: string | number }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white p-4">
      <span className="text-purple-700">{icon}</span>
      <div>
        <p className="text-xs text-slate-500">{label}</p>
        <p className="mt-1 text-lg font-semibold text-slate-900">{value}</p>
      </div>
    </div>
  );
}
