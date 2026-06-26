// DocumentsPage — the landing / document-library screen.
//
// Lists every digitized batch record, surfaces aggregate validation tallies, and
// offers the two entry points into the pipeline: process the bundled sample
// (instant, free) or upload a real PDF (slow, uses API credits). Documents with
// validation errors are visually prioritized so reviewers triage them first.

import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  FileText,
  FilePlus2,
  FlaskConical,
  Info,
  Layers,
  Settings2,
  Sparkles,
  Upload,
} from "lucide-react";
import { api } from "../api/client";
import type { DocumentSummary, ProcessResult } from "../api/types";
import { classNames, useApi, useAsyncAction } from "../lib/ui";
import {
  Card,
  CountPill,
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  Spinner,
  Stat,
  StatusBadge,
} from "../components/atoms";

// --- aggregate helpers ------------------------------------------------------

interface Totals {
  documents: number;
  errors: number;
  warnings: number;
  needsReview: number;
}

function sumTotals(docs: DocumentSummary[]): Totals {
  return docs.reduce<Totals>(
    (acc, d) => ({
      documents: acc.documents + 1,
      errors: acc.errors + d.n_errors,
      warnings: acc.warnings + d.n_warnings,
      needsReview: acc.needsReview + d.n_needs_review,
    }),
    { documents: 0, errors: 0, warnings: 0, needsReview: 0 },
  );
}

// Auto-accepted / clean fields = the ones that did NOT need review. The promise
// is "most fields auto-accept", so showing this good-tone hint keeps the calm.
function autoCount(d: DocumentSummary): number {
  return Math.max(0, d.n_fields - d.n_needs_review);
}

// --- document card ----------------------------------------------------------

function DocumentCard({ doc }: { doc: DocumentSummary }) {
  const hasErrors = doc.n_errors > 0;
  const hasWarnings = !hasErrors && doc.n_warnings > 0;
  const auto = autoCount(doc);

  return (
    <Link
      to={`/documents/${doc.id}`}
      className={classNames(
        "card group flex flex-col gap-3 p-4 transition-all duration-150",
        "hover:-translate-y-0.5 hover:shadow-panel focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40",
        hasErrors && "border-l-4 border-l-rose-400",
        hasWarnings && "border-l-4 border-l-amber-400",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-mono text-[13px] font-semibold text-slate-700">{doc.doc_no}</div>
          <h3 className="mt-0.5 line-clamp-2 text-sm font-medium text-slate-800 group-hover:text-brand-700">
            {doc.title?.trim() || "Untitled batch record"}
          </h3>
        </div>
        <StatusBadge status={statusToFieldStatus(doc.status)} />
      </div>

      <div className="flex items-center gap-3 text-xs text-slate-500">
        <span className="inline-flex items-center gap-1">
          <FileText className="h-3.5 w-3.5 text-slate-400" />
          <span className="tabular-nums">{doc.page_count}</span> pages
        </span>
        <span className="inline-flex items-center gap-1">
          <Layers className="h-3.5 w-3.5 text-slate-400" />
          <span className="tabular-nums">{doc.n_fields}</span> fields
        </span>
      </div>

      <div className="mt-auto flex flex-wrap items-center gap-1.5">
        {doc.n_errors > 0 && <CountPill tone="error" count={doc.n_errors} label="errors" />}
        {doc.n_warnings > 0 && <CountPill tone="warning" count={doc.n_warnings} label="warnings" />}
        {doc.n_needs_review > 0 && (
          <CountPill tone="neutral" count={doc.n_needs_review} label="to review" />
        )}
        {doc.n_errors === 0 && doc.n_warnings === 0 && doc.n_needs_review === 0 ? (
          <CountPill tone="good" count={auto} label="auto-accepted" />
        ) : (
          <span className="inline-flex items-center gap-1 text-xs text-brand-600">
            <Sparkles className="h-3.5 w-3.5" />
            <span className="tabular-nums">{auto}</span> auto
          </span>
        )}
      </div>
    </Link>
  );
}

// DocumentStatus and FieldStatus differ; map to the closest badge so we can reuse
// the frozen StatusBadge atom rather than hand-rolling a second badge.
function statusToFieldStatus(s: DocumentSummary["status"]) {
  switch (s) {
    case "processed":
      return "validated" as const;
    case "processing":
      return "extracted" as const;
    case "failed":
      return "needs_review" as const;
    case "uploaded":
    default:
      return "extracted" as const;
  }
}

// --- page -------------------------------------------------------------------

export default function DocumentsPage() {
  const navigate = useNavigate();
  const { data, loading, error, reload } = useApi(() => api.listDocuments(), []);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [maxPages, setMaxPages] = useState<string>("");
  const [uploadStep, setUploadStep] = useState<string | null>(null);

  function parsedMaxPages(): number | undefined {
    const n = parseInt(maxPages, 10);
    return Number.isFinite(n) && n > 0 ? n : undefined;
  }

  // After a successful pipeline run: refresh the list and jump into review.
  function onProcessed(res: ProcessResult | undefined) {
    if (!res) return;
    reload();
    navigate(`/documents/${res.document_id}`);
  }

  // (a) Process the bundled sample — the stub ignores source_path, so this is
  // instant and free. max_pages still applies for a consistent UX.
  const processSample = useAsyncAction(async () => {
    const res = await api.processDocument({ max_pages: parsedMaxPages() });
    onProcessed(res);
    return res;
  });

  // (b) Upload a real PDF, then process it. Two network steps with progress text.
  const uploadFlow = useAsyncAction(async (file: File) => {
    setUploadStep("Uploading PDF…");
    const { source_path } = await api.uploadDocument(file);
    setUploadStep("Processing pages…");
    const res = await api.processDocument({ source_path, max_pages: parsedMaxPages() });
    setUploadStep(null);
    onProcessed(res);
    return res;
  });

  const busy = processSample.pending || uploadFlow.pending;
  const actionError = processSample.error || uploadFlow.error;

  function pickFile() {
    fileInputRef.current?.click();
  }

  async function onFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    // Reset so choosing the same file again re-triggers change.
    e.target.value = "";
    if (!file) return;
    await uploadFlow.run(file);
  }

  const totals = data ? sumTotals(data) : null;

  return (
    <div className="animate-fade-in space-y-6">
      {/* Header + primary actions */}
      <header className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Batch Records</h1>
          <p className="mt-1 max-w-xl text-sm text-slate-500">
            Digitized handwritten batch-production records. Most fields auto-accept; the uncertain
            ones go to a review queue — right or it asks, never silently wrong.
          </p>
        </div>

        <div className="flex flex-col items-stretch gap-2 sm:items-end">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 py-1">
              <label htmlFor="maxPages" className="text-xs text-slate-500">
                max pages
              </label>
              <input
                id="maxPages"
                type="number"
                min={1}
                inputMode="numeric"
                placeholder="all"
                value={maxPages}
                onChange={(e) => setMaxPages(e.target.value)}
                disabled={busy}
                className="w-16 rounded-md border border-slate-200 bg-white px-1.5 py-1 text-right text-sm tabular-nums text-slate-700 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
              />
            </div>

            <button
              type="button"
              onClick={pickFile}
              disabled={busy}
              className="btn-secondary"
              title="Upload a PDF, then run the pipeline"
            >
              {uploadFlow.pending ? <Spinner /> : <Upload className="h-4 w-4" />}
              Upload PDF
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={onFileChosen}
            />

            <button
              type="button"
              onClick={() => processSample.run()}
              disabled={busy}
              className="btn-primary"
              title="Run the bundled sample through the pipeline"
            >
              {processSample.pending ? <Spinner /> : <FlaskConical className="h-4 w-4" />}
              Process sample
            </button>
          </div>

          {/* progress text for the multi-step upload flow */}
          {uploadFlow.pending && uploadStep && (
            <div className="inline-flex items-center gap-2 text-xs font-medium text-brand-700">
              <Spinner className="h-3.5 w-3.5" /> {uploadStep}
            </div>
          )}

          {/* credits / timing note */}
          <p className="flex items-start gap-1.5 text-xs text-slate-400 sm:text-right">
            <Info className="mt-px h-3.5 w-3.5 shrink-0" />
            <span>
              The bundled sample is instant and free. Processing a real 46-page PDF with live cloud
              providers can take a while and uses API credits — set <em>max pages</em> for a cheap
              first run.
            </span>
          </p>

          {actionError && (
            <p className="inline-flex items-start gap-1.5 text-xs font-medium text-rose-600 sm:text-right">
              <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" /> {actionError}
            </p>
          )}
        </div>
      </header>

      {/* Aggregate summary */}
      {totals && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Documents" value={totals.documents} tone="neutral" />
          <Stat label="Errors" value={totals.errors} tone="error" hint="across all records" />
          <Stat label="Warnings" value={totals.warnings} tone="warning" hint="across all records" />
          <Stat
            label="Needs review"
            value={totals.needsReview}
            tone={totals.needsReview > 0 ? "warning" : "good"}
            hint="fields in queue"
          />
        </div>
      )}

      {/* List / states */}
      {loading ? (
        <Card className="p-2">
          <LoadingBlock label="Loading batch records…" />
        </Card>
      ) : error ? (
        <ErrorBlock
          message={`${error} — check the backend API settings (the gear in the top bar).`}
          onRetry={reload}
        />
      ) : !data || data.length === 0 ? (
        <EmptyState
          icon={<FilePlus2 className="h-8 w-8" />}
          title="No batch records yet"
          hint="Process the bundled sample to see the full digitize → validate → review flow. It's instant and free."
          action={
            <button
              type="button"
              onClick={() => processSample.run()}
              disabled={busy}
              className="btn-primary mt-1"
            >
              {processSample.pending ? <Spinner /> : <FlaskConical className="h-4 w-4" />}
              Process sample
            </button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {[...data]
            // Errors first, then warnings, then anything still in review — same
            // triage priority the product promises in the review queue.
            .sort(
              (a, b) =>
                b.n_errors - a.n_errors ||
                b.n_warnings - a.n_warnings ||
                b.n_needs_review - a.n_needs_review,
            )
            .map((doc) => (
              <DocumentCard key={doc.id} doc={doc} />
            ))}
        </div>
      )}

      {/* subtle pointer to API settings, mirroring Layout's gear */}
      {error && (
        <p className="flex items-center justify-center gap-1.5 text-xs text-slate-400">
          <Settings2 className="h-3.5 w-3.5" /> Backend at the top-right gear can be retargeted
          without a rebuild.
        </p>
      )}
    </div>
  );
}
