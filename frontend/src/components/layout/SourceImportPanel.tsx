import { useEffect, useRef, useState, type FormEvent } from "react";
import { Check, FileText, Link2, LoaderCircle, UploadCloud, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { ingestApi } from "../../services/apiClient";

type ImportMode = "upload" | "url";
type FileState = "queued" | "importing" | "imported" | "quarantined" | "failed";

interface IngestResult {
  accepted: boolean;
  quarantined: boolean;
  error?: string | null;
  doc_sha256?: string | null;
}

interface FileResult {
  id: string;
  name: string;
  state: FileState;
  detail?: string;
}

interface SelectedFile {
  id: string;
  file: File;
}

function fileId(file: File) {
  return `${file.name}\u0000${file.size}\u0000${file.lastModified}`;
}

function errorMessage(error: unknown) {
  const response = (error as { response?: { data?: { detail?: string; error?: string } } }).response;
  return response?.data?.detail || response?.data?.error || "Import failed. Check the source and try again.";
}

export default function SourceImportPanel() {
  const [mode, setMode] = useState<ImportMode>("upload");
  const [files, setFiles] = useState<SelectedFile[]>([]);
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [progress, setProgress] = useState("");
  const [summary, setSummary] = useState("");
  const [results, setResults] = useState<FileResult[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (startedAt === null) return;
    const updateElapsed = () => setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    updateElapsed();
    const interval = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(interval);
  }, [startedAt]);

  function updateResult(id: string, result: FileResult) {
    setResults((current) => current.some((item) => item.id === id)
      ? current.map((item) => item.id === id ? result : item)
      : [...current, result]);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || (mode === "upload" && !files.length) || (mode === "url" && !url.trim())) return;
    setBusy(true);
    setStartedAt(Date.now());
    setElapsedSeconds(0);
    setSummary("");

    const sources = mode === "upload" ? files : [{ id: "url", file: null }];
    const entries: FileResult[] = sources.map((entry) => ({
      id: entry.id,
      name: entry.file?.name ?? (title.trim() || url.trim()),
      state: "queued",
    }));
    setResults((current) => [
      ...current.filter((result) => !entries.some((entry) => entry.id === result.id)),
      ...entries,
    ]);

    let imported = 0;
    let quarantined = 0;
    let failed = 0;

    const failedFiles: SelectedFile[] = [];
    for (const [index, entry] of sources.entries()) {
      const { id } = entry;
      const file = entry.file;
      const name = file?.name ?? (title.trim() || url.trim());
      setProgress(`Importing ${index + 1} of ${sources.length}: ${name}`);
      updateResult(id, { id, name, state: "importing" });

      if (file && file.size > 25 * 1024 * 1024) {
        failed += 1;
        failedFiles.push(entry as SelectedFile);
        updateResult(id, { id, name, state: "failed", detail: "File exceeds the 25 MB per-file limit." });
        continue;
      }

      const form = new FormData();
      if (file) {
        form.append("file", file);
        form.append("title", title.trim() || file.name);
      } else {
        form.append("url", url.trim());
        if (title.trim()) form.append("title", title.trim());
      }

      try {
        const response = await ingestApi.document(form);
        const result = response.data as IngestResult;
        if (result.quarantined) {
          quarantined += 1;
          updateResult(id, { id, name, state: "quarantined", detail: "Uploaded and held for review; not added to the compiled graph." });
        } else if (!result.accepted || result.error) {
          failed += 1;
          if (file) failedFiles.push(entry as SelectedFile);
          updateResult(id, { id, name, state: "failed", detail: result.error || "The source could not be compiled." });
        } else {
          imported += 1;
          updateResult(id, { id, name, state: "imported", detail: result.doc_sha256 ? `SHA-256 ${result.doc_sha256}` : "Compiled into this project." });
        }
      } catch (error) {
        failed += 1;
        if (file) failedFiles.push(entry as SelectedFile);
        updateResult(id, { id, name, state: "failed", detail: errorMessage(error) });
      }
    }

    try {
      setProgress("");
      const outcome = [
        imported ? `${imported} imported` : "",
        quarantined ? `${quarantined} quarantined` : "",
        failed ? `${failed} failed` : "",
      ].filter(Boolean).join(", ");
      setSummary(`${outcome || "No sources were imported."}${failedFiles.length ? " · Failed files remain selected so you can retry or remove them." : ""}`);
      if (mode === "upload") {
        setFiles(failedFiles);
        if (fileInput.current) fileInput.current.value = "";
      } else if (imported > 0 || quarantined > 0) {
        setUrl("");
        setTitle("");
      }
      if (imported > 0) void queryClient.invalidateQueries();
    } finally {
      setBusy(false);
      setStartedAt(null);
    }
  }

  function removeFile(index: number) {
    const removed = files[index];
    setFiles((current) => current.filter((_, fileIndex) => fileIndex !== index));
    if (removed) setResults((current) => current.filter((result) => result.id !== removed.id));
    if (fileInput.current) fileInput.current.value = "";
    setSummary("");
  }

  return (
    <section className="card" aria-label="Add a source to this project">
      <div className="flex items-center gap-2">
        <UploadCloud size={16} className="text-blue-700" />
        <h3 className="font-semibold text-sm">Add source to this project</h3>
      </div>
      <p className="mt-1 text-xs leading-5 text-gray-500">The source is compiled into the selected project’s private graph and vault.</p>

      <div className="mt-3 flex gap-2" role="tablist" aria-label="Source import method">
        <button type="button" role="tab" aria-selected={mode === "upload"} disabled={busy} className={`btn btn-sm ${mode === "upload" ? "btn-primary" : "btn-secondary"}`} onClick={() => setMode("upload")}>
          <UploadCloud size={13} className="mr-1" /> Upload files
        </button>
        <button type="button" role="tab" aria-selected={mode === "url"} disabled={busy} className={`btn btn-sm ${mode === "url" ? "btn-primary" : "btn-secondary"}`} onClick={() => setMode("url")}>
          <Link2 size={13} className="mr-1" /> From URL
        </button>
      </div>

      <form className="mt-3 space-y-2" onSubmit={(event) => void submit(event)}>
        {mode === "upload" ? (
          <>
            <input
              ref={fileInput}
              aria-label="Choose source files"
              className="block w-full text-xs text-gray-600 file:mr-2 file:rounded file:border-0 file:bg-blue-50 file:px-2 file:py-1.5 file:text-xs file:font-medium file:text-blue-700 hover:file:bg-blue-100"
              type="file"
              multiple
              accept=".pdf,.docx,.txt,.html,.htm,.md,.csv"
              disabled={busy}
              onChange={(event) => {
                const additions = Array.from(event.target.files ?? []).map((file) => ({ id: fileId(file), file }));
                if (additions.length) {
                  setFiles((current) => {
                    const existing = new Set(current.map((entry) => entry.id));
                    return [...current, ...additions.filter((entry) => !existing.has(entry.id))];
                  });
                }
                event.target.value = "";
                setSummary("");
              }}
            />
            {files.length > 0 && (
              <ul className="max-h-32 space-y-1 overflow-y-auto rounded bg-slate-50 p-2" aria-label="Selected files">
                {files.map(({ id, file }, index) => (
                  <li key={id} className="flex items-center gap-1.5 text-[11px] text-slate-700">
                    <FileText size={12} className="shrink-0 text-slate-400" />
                    <span className="min-w-0 flex-1 truncate" title={file.name}>{file.name}</span>
                    <span className="shrink-0 text-slate-400">{(file.size / (1024 * 1024)).toFixed(1)} MB</span>
                    <button type="button" className="shrink-0 text-slate-400 hover:text-red-600" disabled={busy} aria-label={`Remove ${file.name}`} onClick={() => removeFile(index)}><X size={13} /></button>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <input
            aria-label="Source URL"
            className="input w-full text-xs"
            type="url"
            placeholder="https://example.org/report"
            value={url}
            disabled={busy}
            onChange={(event) => setUrl(event.target.value)}
          />
        )}
        <input
          aria-label="Source title (optional)"
          className="input w-full text-xs"
          type="text"
          maxLength={300}
          placeholder={mode === "upload" ? "Title for all selected files (optional)" : "Title (optional)"}
          value={title}
          disabled={busy}
          onChange={(event) => setTitle(event.target.value)}
        />
        <button className="btn btn-primary btn-sm w-full justify-center" type="submit" disabled={busy || (mode === "upload" ? !files.length : !url.trim())}>
          {busy ? "Importing…" : mode === "upload" ? `${results.some((result) => result.state === "failed" && files.some((entry) => entry.id === result.id)) ? "Retry" : "Import"} ${files.length || "files"} ${files.length === 1 ? "file" : "files"} into project` : "Import URL into project"}
        </button>
        <p className="text-[10px] leading-4 text-gray-400">PDF, DOCX, TXT, HTML, Markdown, or CSV; up to 25 MB each. Files import one at a time so each gets its own review result. URL imports accept public HTTP(S) pages.</p>
      </form>

      {(progress || summary) && (
        <div className="mt-3 flex items-center gap-2 rounded bg-blue-50 px-2.5 py-2 text-xs text-blue-800" role="status" aria-live="polite">
          {busy && <LoaderCircle size={15} className="shrink-0 animate-spin" aria-label="Import in progress" />}
          <span className="min-w-0 flex-1">{progress || summary}</span>
          {busy && <span className="shrink-0 tabular-nums text-blue-600">Running · {String(Math.floor(elapsedSeconds / 60)).padStart(2, "0")}:{String(elapsedSeconds % 60).padStart(2, "0")}</span>}
        </div>
      )}
      {results.length > 0 && (
        <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto" aria-label="Import results">
          {results.map((result) => (
            <li key={result.id} className="rounded border border-slate-100 px-2 py-1.5 text-[10px] leading-4">
              <div className="flex items-center gap-1.5">
                {result.state === "imported" ? <Check size={12} className="text-green-700" /> : <FileText size={12} className={result.state === "failed" ? "text-red-600" : result.state === "quarantined" ? "text-amber-600" : "text-slate-400"} />}
                <span className="min-w-0 flex-1 truncate font-medium text-slate-700" title={result.name}>{result.name}</span>
                <span className={result.state === "failed" ? "text-red-700" : result.state === "quarantined" ? "text-amber-700" : result.state === "imported" ? "text-green-700" : "text-slate-500"}>
                  {result.state === "importing" ? "Importing" : result.state === "queued" ? "Queued" : result.state === "imported" ? "Imported" : result.state === "quarantined" ? "Quarantined" : "Failed"}
                </span>
              </div>
              {result.detail && <p className="mt-0.5 break-all pl-4 text-slate-500">{result.detail}</p>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
