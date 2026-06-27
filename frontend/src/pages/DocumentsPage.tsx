// DocumentsPage — the landing / document-library screen.
//
// Lists every digitized batch record, surfaces aggregate validation tallies, and
// offers the two entry points into the pipeline: process the bundled sample
// (instant, free) or upload a real PDF (slow, uses API credits). Documents with
// validation errors are visually prioritized so reviewers triage them first.

import { useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  CheckSquare,
  FileText,
  FilePlus2,
  FlaskConical,
  Gauge,
  GitCompareArrows,
  Info,
  Layers,
  Settings2,
  Sparkles,
  Square,
  Trash2,
  TrendingUp,
  Upload,
  X,
} from "lucide-react";
import { api } from "../api/client";
import type { DocumentSummary, ProcessResult } from "../api/types";
import {
  classNames,
  displayDocNo,
  isSimulatedDoc,
  prettyDocTitle,
  useApi,
  useAsyncAction,
} from "../lib/ui";
import {
  Card,
  CountPill,
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  SimulatedBadge,
  Spinner,
  StatusBadge,
} from "../components/atoms";
import EvalModal from "./review/EvalModal";

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

// --- "Yield": rough review effort/cost the tool saves ----------------------
// A deliberately simple, clearly-approximate model. Baseline: a team manually
// reviewing EVERY page to release the record; the tool auto-clears the pages with
// no flags, leaving only the flagged ones for a human.
const REVIEW_MIN_PER_PAGE = 8; // minutes a person spends checking one handwritten page
const REVIEWER_EUR_PER_HOUR = 80; // loaded cost of a GMP reviewer
const REVIEW_TEAM = 10; // reviewers in parallel — affects turnaround, not cost

interface YieldEstimate {
  hours: number;
  cost: number;
  savedPages: number;
  flaggedPages: number;
  totalPages: number;
  turnaroundH: number;
}

function computeYield(docs: DocumentSummary[]): YieldEstimate {
  let totalPages = 0;
  let flaggedPages = 0;
  for (const d of docs) {
    totalPages += d.page_count;
    // Approximate flagged pages from the share of fields still needing review.
    const frac = d.n_fields > 0 ? d.n_needs_review / d.n_fields : 0;
    flaggedPages += Math.min(d.page_count, Math.ceil(d.page_count * frac));
  }
  const savedPages = Math.max(0, totalPages - flaggedPages);
  const hours = (savedPages * REVIEW_MIN_PER_PAGE) / 60;
  return {
    hours,
    cost: hours * REVIEWER_EUR_PER_HOUR,
    savedPages,
    flaggedPages,
    totalPages,
    turnaroundH: hours / REVIEW_TEAM,
  };
}

function YieldPill({ y }: { y: YieldEstimate }) {
  const hours = y.hours >= 10 ? Math.round(y.hours).toString() : y.hours.toFixed(1);
  const cost = Math.round(y.cost).toLocaleString();
  const turn = y.turnaroundH >= 10 ? Math.round(y.turnaroundH).toString() : y.turnaroundH.toFixed(1);
  return (
    <span
      className="inline-flex items-center gap-2 rounded-lg bg-brand-50 px-2.5 py-1 ring-1 ring-inset ring-brand-100"
      title={
        `Approximation. Baseline: a ${REVIEW_TEAM}-person team manually reviewing all ` +
        `${y.totalPages} pages to release the records, at ~${REVIEW_MIN_PER_PAGE} min/page ` +
        `(€${REVIEWER_EUR_PER_HOUR}/h). The tool auto-clears ${y.savedPages} pages; ~${y.flaggedPages} ` +
        `still need a human. Saves ≈${hours} review-hours (€${cost}), ~${turn}h turnaround across ${REVIEW_TEAM} reviewers.`
      }
    >
      <TrendingUp className="h-4 w-4 text-brand-600" />
      <span className="text-sm font-semibold text-brand-700">Yield</span>
      <span className="text-sm font-medium tabular-nums text-brand-700">
        ≈ {hours} h · €{cost}
      </span>
      <span className="text-[11px] font-normal text-brand-400">approx</span>
    </span>
  );
}

// One inline figure in the slim summary strip: big number + muted label.
function SummaryStat({
  n,
  label,
  tone,
}: {
  n: number;
  label: string;
  tone: "error" | "warning" | "good" | "neutral";
}) {
  const color =
    n === 0
      ? "text-slate-400"
      : tone === "error"
        ? "text-rose-600"
        : tone === "warning"
          ? "text-amber-600"
          : tone === "good"
            ? "text-brand-600"
            : "text-slate-800";
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span className={classNames("text-lg font-bold tabular-nums", color)}>{n}</span>
      <span className="text-sm text-slate-400">{label}</span>
    </span>
  );
}

// --- document card ----------------------------------------------------------

function DocumentCard({
  doc,
  selectable = false,
  selected = false,
  onToggle,
  onDelete,
}: {
  doc: DocumentSummary;
  selectable?: boolean;
  selected?: boolean;
  onToggle?: (id: string) => void;
  onDelete?: (doc: DocumentSummary) => void;
}) {
  const hasErrors = doc.n_errors > 0;
  const hasWarnings = !hasErrors && doc.n_warnings > 0;
  const auto = autoCount(doc);
  const sim = isSimulatedDoc(doc);

  const base = classNames(
    "card group flex flex-col gap-3 p-4 text-left transition-all duration-150",
    "focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40",
    hasErrors && "border-l-4 border-l-rose-400",
    hasWarnings && "border-l-4 border-l-amber-400",
    selected && "ring-2 ring-brand-500",
    !selected && "hover:-translate-y-0.5 hover:shadow-panel",
  );

  const inner = (
    <>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-mono text-[13px] font-semibold text-slate-700">{displayDocNo(doc.doc_no)}</div>
          <h3 className="mt-0.5 line-clamp-2 text-sm font-medium text-slate-800 group-hover:text-brand-700">
            {prettyDocTitle(doc.title)}
          </h3>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          {selectable &&
            (selected ? (
              <CheckSquare className="h-5 w-5 text-brand-600" />
            ) : (
              <Square className="h-5 w-5 text-slate-300" />
            ))}
          <StatusBadge status={statusToFieldStatus(doc.status)} />
          {sim && <SimulatedBadge />}
        </div>
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
    </>
  );

  const deleteBtn = onDelete && (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onDelete(doc);
      }}
      title="Delete batch record"
      aria-label="Delete batch record"
      className="absolute -right-2 -top-2 z-10 hidden h-7 w-7 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-400 shadow-sm transition-colors hover:border-rose-300 hover:bg-rose-50 hover:text-rose-600 group-hover:flex"
    >
      <Trash2 className="h-3.5 w-3.5" />
    </button>
  );

  return (
    <div className="group relative">
      {selectable ? (
        <button type="button" onClick={() => onToggle?.(doc.id)} aria-pressed={selected} className={base}>
          {inner}
        </button>
      ) : (
        <Link to={`/documents/${doc.id}`} className={base}>
          {inner}
        </Link>
      )}
      {deleteBtn}
    </div>
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
  // A PDF must be uploaded before processing is allowed. Holds the staged upload.
  const [uploaded, setUploaded] = useState<{ source_path: string; filename: string } | null>(null);
  // Compare mode: pick ≥2 batches, then open them side by side.
  const [compareMode, setCompareMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

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

  // (a) Upload a PDF and STAGE it (no auto-processing) so the Process button only
  // becomes available once a document is present.
  const uploadAction = useAsyncAction(async (file: File) => {
    setUploadStep("Uploading…");
    const res = await api.uploadDocument(file);
    setUploaded({ source_path: res.source_path, filename: res.filename });
    setUploadStep(null);
    return res;
  });

  // (b) Process the staged upload. Disabled until something is uploaded.
  const processAction = useAsyncAction(async () => {
    if (!uploaded) return undefined;
    setUploadStep("Processing pages…");
    const res = await api.processDocument({ source_path: uploaded.source_path, max_pages: parsedMaxPages() });
    setUploadStep(null);
    setUploaded(null);
    onProcessed(res);
    return res;
  });

  // (c) Create a simulated demo batch (no upload, no API). Stays on the page so the
  // new entry shows up in the library immediately.
  const simulateAction = useAsyncAction(async () => {
    const res = await api.simulateDocument();
    reload();
    return res;
  });

  const deleteAction = useAsyncAction(async (id: string) => {
    await api.deleteDocument(id);
    reload();
  });

  function onDeleteDoc(doc: DocumentSummary) {
    if (
      window.confirm(
        `Delete "${prettyDocTitle(doc.title)}"? This permanently removes the batch record and all its data.`,
      )
    ) {
      deleteAction.run(doc.id);
    }
  }

  const busy = uploadAction.pending || processAction.pending || simulateAction.pending;
  const actionError = uploadAction.error || processAction.error || simulateAction.error || deleteAction.error;

  function pickFile() {
    fileInputRef.current?.click();
  }

  async function onFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    // Reset so choosing the same file again re-triggers change.
    e.target.value = "";
    if (!file) return;
    await uploadAction.run(file);
  }

  // --- compare-mode helpers ---
  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  function cancelCompare() {
    setCompareMode(false);
    setSelected(new Set());
  }
  function runCompare() {
    const ids = Array.from(selected);
    if (ids.length >= 2) navigate(`/compare?ids=${ids.join(",")}`);
  }

  const totals = data ? sumTotals(data) : null;
  const yieldEst = data && data.length ? computeYield(data) : null;
  const canCompare = (data?.length ?? 0) >= 2;

  // Eval AI scores the pipeline against the ground-truth set — it's about the AI's
  // quality, not a single batch. Prefer a real (non-simulated) record to score.
  const [evalOpen, setEvalOpen] = useState(false);
  const evalDocId = useMemo(() => {
    if (!data?.length) return null;
    return (data.find((d) => !isSimulatedDoc(d)) ?? data[0]).id;
  }, [data]);

  return (
    <div className="animate-fade-in space-y-6">
      {/* Header + primary actions */}
      <header className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Batch Records</h1>
          <p className="mt-1 text-sm text-slate-500">
            Digitized handwritten records. Uncertain fields go to review, never silently wrong.
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
              onClick={() => simulateAction.run()}
              disabled={busy}
              className="btn-secondary"
              title="Create a simulated demo batch (no upload, offline)"
            >
              {simulateAction.pending ? <Spinner /> : <FlaskConical className="h-4 w-4" />}
              Simulated batch
            </button>

            <button
              type="button"
              onClick={pickFile}
              disabled={busy}
              className="btn-secondary"
              title="Upload a PDF to process"
            >
              {uploadAction.pending ? <Spinner /> : <Upload className="h-4 w-4" />}
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
              onClick={() => processAction.run()}
              disabled={busy || !uploaded}
              className="btn-primary"
              title={uploaded ? "Run the uploaded PDF through the pipeline" : "Upload a PDF first"}
            >
              {processAction.pending ? <Spinner /> : <FlaskConical className="h-4 w-4" />}
              Process
            </button>
          </div>

          {/* staged upload + progress text */}
          {uploadStep ? (
            <div className="inline-flex items-center gap-2 text-xs font-medium text-brand-700">
              <Spinner className="h-3.5 w-3.5" /> {uploadStep}
            </div>
          ) : uploaded ? (
            <div className="inline-flex max-w-xs items-center gap-1.5 text-xs font-medium text-emerald-700">
              <FileText className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{uploaded.filename}</span>
              <span className="text-emerald-600">ready — click Process</span>
            </div>
          ) : null}

          {/* credits / timing note */}
          <p className="flex items-center gap-1.5 text-xs text-slate-400 sm:justify-end">
            <Info className="h-3.5 w-3.5 shrink-0" />
            <span>Upload a PDF to process. Live extraction uses API credits; set <em>max pages</em> to cap.</span>
          </p>

          {actionError && (
            <p className="inline-flex items-start gap-1.5 text-xs font-medium text-rose-600 sm:text-right">
              <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" /> {actionError}
            </p>
          )}
        </div>
      </header>

      {/* Aggregate summary — one slim strip rather than four big cards. */}
      {totals && totals.documents > 0 && (
        <div className="card flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5">
          <SummaryStat n={totals.documents} label={totals.documents === 1 ? "document" : "documents"} tone="neutral" />
          <span className="h-5 w-px bg-slate-200" />
          <SummaryStat n={totals.errors} label="errors" tone="error" />
          <SummaryStat n={totals.warnings} label="warnings" tone="warning" />
          <SummaryStat n={totals.needsReview} label="to review" tone={totals.needsReview > 0 ? "warning" : "good"} />
          <div className="ml-auto flex flex-wrap items-center gap-3">
            {evalDocId && (
              <button type="button" onClick={() => setEvalOpen(true)} className="btn-secondary text-xs">
                <Gauge className="h-3.5 w-3.5" /> Eval AI
              </button>
            )}
            {yieldEst && yieldEst.totalPages > 0 && <YieldPill y={yieldEst} />}
          </div>
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
          hint="Upload a batch-record PDF to run the full digitize → validate → review flow — or add a simulated demo batch to explore it offline."
          action={
            <div className="mt-1 flex flex-wrap items-center justify-center gap-2">
              <button type="button" onClick={pickFile} disabled={busy} className="btn-primary">
                {uploadAction.pending ? <Spinner /> : <Upload className="h-4 w-4" />}
                Upload PDF
              </button>
              <button type="button" onClick={() => simulateAction.run()} disabled={busy} className="btn-secondary">
                {simulateAction.pending ? <Spinner /> : <FlaskConical className="h-4 w-4" />}
                Simulated batch
              </button>
            </div>
          }
        />
      ) : (
        <>
          {/* Compare toolbar */}
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs text-slate-400">
              {data.length} batch{data.length !== 1 ? "es" : ""}
            </p>
            {!compareMode ? (
              canCompare && (
                <button type="button" onClick={() => setCompareMode(true)} className="btn-secondary text-sm">
                  <GitCompareArrows className="h-4 w-4" /> Compare batches
                </button>
              )
            ) : (
              <div className="flex items-center gap-2">
                <span className="hidden text-xs text-slate-500 sm:inline">
                  {selected.size} selected · pick 2+
                </span>
                <button
                  type="button"
                  onClick={runCompare}
                  disabled={selected.size < 2}
                  className="btn-primary text-sm"
                >
                  <GitCompareArrows className="h-4 w-4" /> Compare{selected.size > 0 ? ` (${selected.size})` : ""}
                </button>
                <button type="button" onClick={cancelCompare} className="btn-ghost text-sm">
                  <X className="h-4 w-4" /> Cancel
                </button>
              </div>
            )}
          </div>

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
                <DocumentCard
                  key={doc.id}
                  doc={doc}
                  selectable={compareMode}
                  selected={selected.has(doc.id)}
                  onToggle={toggleSelect}
                  onDelete={compareMode ? undefined : onDeleteDoc}
                />
              ))}
          </div>
        </>
      )}

      {/* subtle pointer to API settings, mirroring Layout's gear */}
      {error && (
        <p className="flex items-center justify-center gap-1.5 text-xs text-slate-400">
          <Settings2 className="h-3.5 w-3.5" /> Backend at the top-right gear can be retargeted
          without a rebuild.
        </p>
      )}

      {evalOpen && evalDocId && <EvalModal documentId={evalDocId} onClose={() => setEvalOpen(false)} />}
    </div>
  );
}
