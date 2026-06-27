// Pipeline trace — a GxP audit/provenance view of HOW a field's value was
// derived, reconstructed purely from the existing `field` object (no new API
// calls). Renders a collapsible vertical timeline of the five pipeline stages:
// Recognition → Normalization → Resolution → Validation → Decision.

import { useState, type ReactNode } from "react";
import {
  ScanLine,
  Wand2,
  GitBranch,
  ShieldCheck,
  CircleCheck,
  ChevronDown,
  ArrowRight,
  AlertTriangle,
  type LucideIcon,
} from "lucide-react";
import type { Field } from "../../api/types";
import { classNames, confidencePct, confidenceTone } from "../../lib/ui";
import {
  CategoryChip,
  ConfidenceMeter,
  SeverityBadge,
  StatusBadge,
} from "../../components/atoms";

function StageRow({
  icon: Icon,
  title,
  tone = "slate",
  isLast = false,
  children,
}: {
  icon: LucideIcon;
  title: string;
  /** accent color for the node bubble */
  tone?: "slate" | "brand" | "amber" | "sky";
  isLast?: boolean;
  children: ReactNode;
}) {
  const bubble = {
    slate: "bg-slate-100 text-slate-500 ring-slate-200",
    brand: "bg-brand-50 text-brand-600 ring-brand-200",
    amber: "bg-amber-50 text-amber-600 ring-amber-200",
    sky: "bg-sky-50 text-sky-600 ring-sky-200",
  }[tone];

  return (
    <li className="relative flex gap-3">
      {/* connector line + node */}
      <div className="flex flex-col items-center">
        <span
          className={classNames(
            "grid h-7 w-7 shrink-0 place-items-center rounded-full ring-1 ring-inset",
            bubble,
          )}
        >
          <Icon className="h-3.5 w-3.5" />
        </span>
        {!isLast && <span className="mt-1 w-px flex-1 bg-slate-200" aria-hidden />}
      </div>
      {/* content */}
      <div className={classNames("min-w-0 flex-1", isLast ? "pb-0" : "pb-4")}>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          {title}
        </h4>
        <div className="mt-1.5 text-sm text-slate-700">{children}</div>
      </div>
    </li>
  );
}

const muted = "text-slate-400";

/** raw → normalized arrow display. */
function Transition({ from, to }: { from: ReactNode; to: ReactNode }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-500">
        {from}
      </code>
      <ArrowRight className="h-3.5 w-3.5 shrink-0 text-slate-400" />
      <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-700">
        {to}
      </code>
    </span>
  );
}

export default function PipelineTrace({ field }: { field: Field }) {
  const [open, setOpen] = useState(false);

  const reads = field.reads ?? [];
  const flags = field.flags ?? [];

  // --- 1. Recognition: do the ensemble reads disagree on the raw value? ------
  const distinctReads = new Set(
    reads.map((r) => (r.value_raw ?? "").trim()).filter((v) => v.length > 0),
  );
  const readsDisagree = distinctReads.size > 1;

  // --- 2. Normalization: did raw differ from normalized? ---------------------
  const raw = field.value_raw ?? null;
  const norm = field.value ?? null;
  const normalized = raw != null && norm != null && raw !== norm;
  const hasNormMeta =
    field.value_type != null || field.unit != null || field.nks != null;

  // --- 3. Resolution: field.value_raw vs the first read's raw ----------------
  const firstReadRaw = reads[0]?.value_raw ?? null;
  const corrected =
    firstReadRaw != null && raw != null && firstReadRaw !== raw;

  // --- 5. Decision rationale -------------------------------------------------
  const tone = confidenceTone(field.confidence);
  const rationale =
    field.status === "auto_accepted"
      ? "clean + confident → auto-accepted"
      : field.status === "needs_review"
        ? "flagged or below confidence → routed to review"
        : field.status === "confirmed" || field.status === "corrected"
          ? "resolved by reviewer"
          : field.status === "validated"
            ? "checks run → awaiting routing"
            : "extracted → pending validation";

  return (
    <div className="card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-3 text-left transition-colors hover:bg-slate-50"
      >
        <GitBranch className="h-4 w-4 shrink-0 text-slate-400" />
        <span className="text-sm font-semibold text-slate-700">Pipeline trace</span>
        <span className="hidden text-xs text-slate-400 sm:inline">
          · how this value was derived
        </span>
        <ChevronDown
          className={classNames(
            "ml-auto h-4 w-4 shrink-0 text-slate-400 transition-transform",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
        <div className="animate-fade-in border-t border-slate-100 px-4 pb-4 pt-4">
          <ol className="space-y-0">
            {/* 1. Recognition */}
            <StageRow icon={ScanLine} title="Recognition" tone="brand">
              {reads.length === 0 ? (
                <span className={muted}>No model reads recorded.</span>
              ) : (
                <div className="space-y-2">
                  {readsDisagree && (
                    <span className="chip bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200">
                      <AlertTriangle className="h-3.5 w-3.5" /> models disagree
                    </span>
                  )}
                  <ul className="space-y-1.5">
                    {reads.map((r, i) => (
                      <li key={`${r.model}-${i}`} className="flex items-center gap-3">
                        <span
                          className="w-16 shrink-0 truncate font-mono text-xs text-slate-500"
                          title={r.model}
                        >
                          {r.model}
                        </span>
                        <span className="min-w-0 flex-1 truncate font-mono text-xs text-slate-700">
                          {r.value_raw ?? "—"}
                        </span>
                        <ConfidenceMeter
                          confidence={r.confidence}
                          className="w-24 shrink-0"
                        />
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </StageRow>

            {/* 2. Normalization */}
            <StageRow icon={Wand2} title="Normalization" tone="sky">
              {normalized ? (
                <div className="space-y-1.5">
                  <Transition from={raw} to={norm} />
                </div>
              ) : (
                <span className={muted}>No change applied.</span>
              )}
              {hasNormMeta && (
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
                  {field.value_type != null && (
                    <span>
                      type:{" "}
                      <span className="font-mono text-slate-600">{field.value_type}</span>
                    </span>
                  )}
                  {field.unit != null && (
                    <span>
                      unit: <span className="font-mono text-slate-600">{field.unit}</span>
                    </span>
                  )}
                  {field.nks != null && (
                    <span>
                      decimals:{" "}
                      <span className="font-mono tabular-nums text-slate-600">
                        {field.nks}
                      </span>
                    </span>
                  )}
                </div>
              )}
            </StageRow>

            {/* 3. Resolution */}
            <StageRow icon={GitBranch} title="Resolution" tone="sky">
              {corrected ? (
                <div className="space-y-1.5">
                  <Transition from={firstReadRaw} to={raw} />
                  <span className="chip bg-sky-50 text-sky-700 ring-1 ring-inset ring-sky-200">
                    snapped to registry / corrected
                  </span>
                </div>
              ) : (
                <span className={muted}>No correction applied.</span>
              )}
            </StageRow>

            {/* 4. Validation */}
            <StageRow
              icon={ShieldCheck}
              title="Validation"
              tone={flags.length === 0 ? "brand" : "amber"}
            >
              {flags.length === 0 ? (
                <span className="inline-flex items-center gap-1.5 font-medium text-brand-700">
                  <ShieldCheck className="h-4 w-4" /> Passed all checks.
                </span>
              ) : (
                <ul className="space-y-1.5">
                  {flags.map((f) => (
                    <li key={f.id} className="flex flex-wrap items-center gap-1.5">
                      <SeverityBadge severity={f.severity} />
                      <CategoryChip category={f.category} />
                      <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-500">
                        {f.code}
                      </code>
                      <span className="text-xs text-slate-600">{f.message}</span>
                    </li>
                  ))}
                </ul>
              )}
            </StageRow>

            {/* 5. Decision */}
            <StageRow icon={CircleCheck} title="Decision" tone="brand" isLast>
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge status={field.status} />
                  <span
                    className={classNames(
                      "text-xs font-semibold tabular-nums",
                      tone.text,
                    )}
                  >
                    {confidencePct(field.confidence)}% · {tone.label}
                  </span>
                </div>
                <ConfidenceMeter
                  confidence={field.confidence}
                  showLabel={false}
                  className="max-w-[16rem]"
                />
                <p className="text-xs text-slate-500">{rationale}</p>
              </div>
            </StageRow>
          </ol>
        </div>
      )}
    </div>
  );
}
