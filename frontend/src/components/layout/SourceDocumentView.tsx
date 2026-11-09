import { useQuery } from "@tanstack/react-query";
import { FileText, ShieldCheck } from "lucide-react";
import { ingestApi, type SourceDocument } from "../../services/apiClient";

export default function SourceDocumentView({ source }: { source: SourceDocument }) {
  const { data: content, isLoading, error } = useQuery({
    queryKey: ["docs", "content", source.sha256],
    queryFn: async () => (await ingestApi.content(source.sha256)).data,
  });

  return (
    <section className="flex h-full min-h-0 flex-col bg-white" aria-label={`Source file ${source.title || source.sha256}`}>
      <header className="border-b border-slate-200 px-5 py-4">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <FileText size={15} /> Source Vault / {source.domain || "uploaded file"}
        </div>
        <h1 className="mt-1 truncate text-lg font-semibold text-slate-900">{source.title || source.domain || "Source document"}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-500">
          <span>{source.admiralty || "Reliability unclassified"}</span>
          <span>{source.is_quarantined ? "Held for review" : "Compiled source"}</span>
          {source.published_at && <span>Published {source.published_at}</span>}
          <span className="truncate" title={source.sha256}>SHA-256 {source.sha256}</span>
        </div>
      </header>
      <div className="min-h-0 flex-1 overflow-auto bg-slate-50 p-4">
        {isLoading ? (
          <p className="text-sm text-slate-500">Loading extracted source text…</p>
        ) : error ? (
          <p role="alert" className="text-sm text-red-700">Could not read this archived source.</p>
        ) : content ? (
          <pre className="mx-auto max-w-5xl whitespace-pre-wrap break-words rounded border border-slate-200 bg-white p-5 font-mono text-xs leading-6 text-slate-800 shadow-sm">{content}</pre>
        ) : (
          <div className="mx-auto max-w-xl rounded border border-slate-200 bg-white p-5 text-sm text-slate-600">
            <ShieldCheck size={18} className="mb-2 text-blue-600" />
            This source has no extracted text to preview. It remains in the project’s immutable source record.
          </div>
        )}
      </div>
    </section>
  );
}
