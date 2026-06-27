// ComparePage — side-by-side comparison of two or more batch records.
//
// Reached from the landing page's "Compare batches" flow (?ids=a,b,c). Each
// selected document becomes a column; rows are the key validation metrics, with
// the best/worst cell per row highlighted so differences pop at a glance.

import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, GitCompareArrows } from "lucide-react";
import { api } from "../api/client";
import type { DocumentSummary } from "../api/types";
import { classNames, displayDocNo, isSimulatedDoc, prettyDocTitle, useApi } from "../lib/ui";
import { ErrorBlock, LoadingBlock, SimulatedBadge, StatusBadge, EmptyState } from "../components/atoms";

// Same rough model as the landing "Yield" figure.
const MIN_PER_PAGE = 8;

function autoCount(d: DocumentSummary): number {
  return Math.max(0, d.n_fields - d.n_needs_review);
}
function savedHours(d: DocumentSummary): number {
  const frac = d.n_fields > 0 ? d.n_needs_review / d.n_fields : 0;
  const flagged = Math.min(d.page_count, Math.ceil(d.page_count * frac));
  return ((d.page_count - flagged) * MIN_PER_PAGE) / 60;
}

type Better = "low" | "high" | "none";
interface Row {
  label: string;
  get: (d: DocumentSummary) => number;
  better: Better;
  fmt?: (n: number) => string;
}

const ROWS: Row[] = [
  { label: "Pages", get: (d) => d.page_count, better: "none" },
  { label: "Fields", get: (d) => d.n_fields, better: "none" },
  { label: "Errors", get: (d) => d.n_errors, better: "low" },
  { label: "Warnings", get: (d) => d.n_warnings, better: "low" },
  { label: "To review", get: (d) => d.n_needs_review, better: "low" },
  { label: "Auto-accepted", get: autoCount, better: "high" },
  {
    label: "Clean rate",
    get: (d) => (d.n_fields > 0 ? (autoCount(d) / d.n_fields) * 100 : 0),
    better: "high",
    fmt: (n) => `${Math.round(n)}%`,
  },
  {
    label: "Saved review-time",
    get: savedHours,
    better: "high",
    fmt: (n) => `≈${n >= 10 ? Math.round(n) : n.toFixed(1)} h`,
  },
];

/** Which column indices hold the best value for this row (empty when all equal). */
function bestIdx(vals: number[], better: Better): Set<number> {
  if (better === "none" || vals.length < 2) return new Set();
  const distinct = new Set(vals);
  if (distinct.size < 2) return new Set(); // all equal → highlight nothing
  const target = better === "low" ? Math.min(...vals) : Math.max(...vals);
  const out = new Set<number>();
  vals.forEach((v, i) => v === target && out.add(i));
  return out;
}

export default function ComparePage() {
  const [params] = useSearchParams();
  const ids = (params.get("ids") || "").split(",").map((s) => s.trim()).filter(Boolean);

  const { data, loading, error, reload } = useApi<DocumentSummary[]>(async () => {
    const settled = await Promise.allSettled(ids.map((id) => api.getDocument(id)));
    return settled
      .filter((s): s is PromiseFulfilledResult<DocumentSummary> => s.status === "fulfilled")
      .map((s) => s.value);
  }, [ids.join(",")]);

  return (
    <div className="animate-fade-in space-y-4">
      <div className="flex items-center gap-3">
        <Link to="/" className="btn-ghost px-2 py-1.5" title="Back to documents" aria-label="Back to documents">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <h1 className="flex items-center gap-2 text-xl font-bold tracking-tight text-slate-900">
          <GitCompareArrows className="h-5 w-5 text-brand-600" /> Compare batches
        </h1>
      </div>

      {loading ? (
        <LoadingBlock label="Loading batches…" />
      ) : error ? (
        <ErrorBlock message={error} onRetry={reload} />
      ) : !data || data.length < 2 ? (
        <EmptyState
          title="Need at least two batches"
          hint="Go back, click Compare batches, and select two or more records."
          action={
            <Link to="/" className="btn-primary mt-1 text-sm">
              <ArrowLeft className="h-4 w-4" /> Back to documents
            </Link>
          }
        />
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200">
                <th className="sticky left-0 z-10 bg-white p-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                  Metric
                </th>
                {data.map((d) => (
                  <th key={d.id} className="min-w-[180px] p-3 text-left align-top">
                    <Link to={`/documents/${d.id}`} className="group block">
                      <div className="font-mono text-[12px] font-semibold text-slate-600">{displayDocNo(d.doc_no)}</div>
                      <div className="mt-0.5 line-clamp-2 text-[13px] font-semibold text-slate-800 group-hover:text-brand-700">
                        {prettyDocTitle(d.title)}
                      </div>
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                        <StatusBadge status={d.status === "processed" ? "validated" : "extracted"} />
                        {isSimulatedDoc(d) && <SimulatedBadge />}
                      </div>
                    </Link>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row) => {
                const vals = data.map(row.get);
                const best = bestIdx(vals, row.better);
                return (
                  <tr key={row.label} className="border-b border-slate-100 last:border-0">
                    <td className="sticky left-0 z-10 bg-white p-3 font-medium text-slate-500">{row.label}</td>
                    {data.map((d, i) => (
                      <td key={d.id} className="p-3">
                        <span
                          className={classNames(
                            "inline-flex items-center rounded-md px-1.5 py-0.5 font-semibold tabular-nums",
                            best.has(i) ? "bg-emerald-50 text-emerald-700" : "text-slate-700",
                          )}
                        >
                          {row.fmt ? row.fmt(vals[i]) : vals[i]}
                        </span>
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="px-1 text-xs text-slate-400">
        Green marks the best value in each row. “Saved review-time” is a rough approximation
        (~{MIN_PER_PAGE} min/page of manual review that the tool auto-clears).
      </p>
    </div>
  );
}
