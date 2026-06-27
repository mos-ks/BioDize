// Full-screen modal that runs the AI evaluation of the current document against
// the ground truth and renders a scorecard. Opened from DocumentBar. Mirrors the
// overlay/Escape-to-close pattern of PageLightbox; reuses the LoadingBlock /
// ErrorBlock atoms and the useApi fetch-on-mount hook (its reload() powers the
// "Eval now" re-run affordance).

import { useEffect, useState } from "react";
import { RefreshCw, ScanSearch, Sparkles, X } from "lucide-react";
import { api } from "../../api/client";
import type { EvalAggregate, EvalPage } from "../../api/types";
import { ErrorBlock, LoadingBlock } from "../../components/atoms";
import { classNames, useApi } from "../../lib/ui";
import PageBoxesModal from "./PageBoxesModal";

// Bucketed tone for an accuracy ratio (0..1): >=0.9 emerald, >=0.7 amber, else
// rose. Mirrors confidenceTone but uses the thresholds/palette for eval scores.
function scoreTone(ratio: number): string {
  if (ratio >= 0.9) return "text-emerald-600";
  if (ratio >= 0.7) return "text-amber-600";
  return "text-rose-600";
}

function pctLabel(ratio: number | null): string {
  if (ratio === null) return "n/a";
  return `${Math.round(Math.max(0, Math.min(1, ratio)) * 100)}%`;
}

function MetricCard({ label, ratio }: { label: string; ratio: number | null }) {
  const tone = ratio === null ? "text-slate-400" : scoreTone(ratio);
  return (
    <div className="card px-4 py-3">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</div>
      <div className={classNames("mt-1 text-2xl font-bold tabular-nums", tone)}>{pctLabel(ratio)}</div>
    </div>
  );
}

function PageRow({ p, onOpenPage }: { p: EvalPage; onOpenPage: (page: number) => void }) {
  // "PASS" only when rules AND the read values/checkboxes all match the gold —
  // a page can have perfect rules yet misread a value, which still needs a look.
  const misreads = p.value_wrong + p.cb_wrong;
  const pass = p.fp.length === 0 && p.fn.length === 0 && misreads === 0;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-t border-slate-100 px-4 py-2.5 first:border-t-0">
      <button
        type="button"
        onClick={() => onOpenPage(p.page)}
        title={`Open page ${p.page} scan`}
        className="flex w-16 shrink-0 items-center gap-1 text-left text-sm font-semibold text-brand-700 hover:text-brand-800 hover:underline"
      >
        <ScanSearch className="h-3.5 w-3.5" /> P{p.page}
      </button>
      <span
        className={classNames(
          "chip ring-1 ring-inset",
          pass
            ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
            : "bg-rose-50 text-rose-700 ring-rose-200",
        )}
      >
        {pass ? "PASS" : "FAIL"}
      </span>
      <span className="text-xs tabular-nums text-slate-500">
        prec <span className="font-semibold text-slate-700">{pctLabel(p.rule_precision)}</span>
        <span className="mx-1 text-slate-300">·</span>
        rec <span className="font-semibold text-slate-700">{pctLabel(p.rule_recall)}</span>
      </span>
      {p.section && <span className="truncate text-xs text-slate-400">{p.section}</span>}
      <div className="flex flex-wrap items-center gap-1">
        {p.fp.map((code) => (
          <span key={`fp-${code}`} className="chip bg-rose-50 text-rose-700 ring-1 ring-inset ring-rose-200" title="False positive">
            FP {code}
          </span>
        ))}
        {p.fn.map((code) => (
          <span key={`fn-${code}`} className="chip bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200" title="False negative">
            FN {code}
          </span>
        ))}
        {p.value_wrong > 0 && (
          <span className="chip bg-orange-50 text-orange-700 ring-1 ring-inset ring-orange-200" title="Handwriting read differently from the gold value">
            {p.value_wrong} value misread{p.value_wrong > 1 ? "s" : ""}
          </span>
        )}
        {p.cb_wrong > 0 && (
          <span className="chip bg-orange-50 text-orange-700 ring-1 ring-inset ring-orange-200" title="Checkbox state read differently from the gold">
            {p.cb_wrong} checkbox misread{p.cb_wrong > 1 ? "s" : ""}
          </span>
        )}
      </div>
      {/* The exact value differences on this page: what the AI read vs the correct
          (gold) value, so it's unambiguous which number is ours. */}
      {p.value_details?.length > 0 && (
        <div className="mt-1 w-full space-y-0.5 pl-16">
          {p.value_details.map((vd, i) => (
            <div key={i} className="text-xs">
              <span className="text-slate-400">{vd.label}: </span>
              <span className="text-[10px] font-semibold uppercase tracking-wide text-rose-400">AI read </span>
              <span className="font-mono text-rose-600 line-through">{vd.pipeline || "∅"}</span>
              <span className="mx-1.5 text-slate-300">→</span>
              <span className="text-[10px] font-semibold uppercase tracking-wide text-emerald-500">correct </span>
              <span className="font-mono font-semibold text-emerald-700">{vd.gold || "∅"}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CountStat({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <span className="inline-flex items-baseline gap-1.5 rounded-lg bg-slate-50 px-3 py-1.5 ring-1 ring-inset ring-slate-200">
      <span className={classNames("text-lg font-bold tabular-nums", tone)}>{value}</span>
      <span className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</span>
    </span>
  );
}

function Scorecard({
  aggregate,
  pages,
  onOpenPage,
}: {
  aggregate: EvalAggregate;
  pages: EvalPage[];
  onOpenPage: (page: number) => void;
}) {
  return (
    <>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        <MetricCard label="Rule Precision" ratio={aggregate.rule_precision} />
        <MetricCard label="Rule Recall" ratio={aggregate.rule_recall} />
        <MetricCard label="F1" ratio={aggregate.rule_f1} />
        <MetricCard label="Coverage" ratio={aggregate.coverage} />
        <MetricCard label="Value accuracy" ratio={aggregate.value_acc} />
        <MetricCard label="Checkbox accuracy" ratio={aggregate.checkbox_acc} />
        <MetricCard label="Signature accuracy" ratio={aggregate.signature_acc} />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <CountStat label="TP" value={aggregate.tp} tone="text-emerald-600" />
        <CountStat label="FP" value={aggregate.fp} tone="text-rose-600" />
        <CountStat label="FN" value={aggregate.fn} tone="text-amber-600" />
      </div>

      <div className="mt-5">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
          Per-page results
        </h3>
        <div className="card overflow-hidden p-0">
          {pages.length === 0 ? (
            <div className="px-4 py-6 text-center text-sm text-slate-400">No pages evaluated.</div>
          ) : (
            pages.map((p) => <PageRow key={p.page} p={p} onOpenPage={onOpenPage} />)
          )}
        </div>
      </div>
    </>
  );
}

export default function EvalModal({
  documentId,
  onClose,
}: {
  documentId: string;
  onClose: () => void;
}) {
  const { data, loading, error, reload } = useApi(() => api.getEvaluation(documentId), [documentId]);
  const [openPage, setOpenPage] = useState<number | null>(null);

  // Close on Escape; lock body scroll while open. When the page-scan viewer is
  // open, Escape closes that first (not the whole scorecard).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && openPage == null) onClose();
    }
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose, openPage]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="AI evaluation vs ground truth"
      className="fixed inset-0 z-50 flex animate-fade-in items-start justify-center overflow-y-auto bg-slate-900/70 p-4 backdrop-blur-sm sm:p-6"
      onClick={onClose}
    >
      <div
        className="card my-auto w-full max-w-3xl p-5 sm:p-6"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 text-lg font-semibold text-slate-800">
              <Sparkles className="h-5 w-5 text-brand-500" />
              AI Evaluation vs Ground Truth
            </h2>
            {data && (
              <p className="mt-0.5 text-sm text-slate-500">
                Scored against{" "}
                <span className="font-semibold tabular-nums text-slate-700">{data.gold_pages}</span>{" "}
                gold {data.gold_pages === 1 ? "page" : "pages"}.
              </p>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              onClick={reload}
              disabled={loading}
              className="btn-secondary"
              title="Run an updated evaluation"
            >
              <RefreshCw className={classNames("h-4 w-4", loading && "animate-spin")} /> Eval now
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close evaluation"
              title="Close (Esc)"
              className="btn-ghost px-2 py-1.5"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="mt-4">
          {loading ? (
            <LoadingBlock label="Evaluating…" />
          ) : error ? (
            <ErrorBlock message={error} onRetry={reload} />
          ) : data ? (
            <Scorecard aggregate={data.aggregate} pages={data.pages} onOpenPage={setOpenPage} />
          ) : null}
        </div>
      </div>

      {openPage != null && (
        <PageBoxesModal
          documentId={documentId}
          pageNo={openPage}
          fields={[]}
          onClose={() => setOpenPage(null)}
        />
      )}
    </div>
  );
}
