// Shared presentational atoms. Frozen layer — pages compose these.

import type { ReactNode } from "react";
import { Loader2, Inbox, AlertCircle, FlaskConical } from "lucide-react";
import type { Field, FieldStatus, Flag, Severity } from "../api/types";
import {
  categoryMeta,
  classNames,
  confidencePct,
  confidenceTone,
  severityMeta,
  statusMeta,
  worstSeverity,
} from "../lib/ui";

export function SeverityBadge({ severity, size = "sm" }: { severity: Severity; size?: "sm" | "md" }) {
  const m = severityMeta(severity);
  const Icon = m.icon;
  return (
    <span className={classNames("chip", m.badge, size === "md" && "px-2.5 py-1 text-sm")}>
      <Icon className={size === "md" ? "h-4 w-4" : "h-3.5 w-3.5"} />
      {m.label}
    </span>
  );
}

export function StatusBadge({ status }: { status: FieldStatus }) {
  const m = statusMeta(status);
  return (
    <span className={classNames("chip", m.badge)}>
      <span className={classNames("h-1.5 w-1.5 rounded-full", m.dot)} />
      {m.label}
    </span>
  );
}

/** Marks a simulated/demo batch (not a real scanned upload). */
export function SimulatedBadge() {
  return (
    <span className="chip bg-violet-50 text-violet-700 ring-1 ring-inset ring-violet-200">
      <FlaskConical className="h-3.5 w-3.5" />
      Simulated
    </span>
  );
}

export function CategoryChip({ category }: { category: Flag["category"] }) {
  const m = categoryMeta(category);
  const Icon = m.icon;
  return (
    <span className="chip bg-slate-100 text-slate-600 ring-1 ring-inset ring-slate-200">
      <Icon className={classNames("h-3.5 w-3.5", m.color)} />
      {m.label}
    </span>
  );
}

/** Horizontal confidence meter with bucketed color. */
export function ConfidenceMeter({
  confidence,
  showLabel = true,
  className,
}: {
  confidence: number;
  showLabel?: boolean;
  className?: string;
}) {
  const pct = confidencePct(confidence);
  const tone = confidenceTone(confidence);
  return (
    <div className={classNames("flex items-center gap-2", className)}>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className={classNames("h-full rounded-full transition-all", tone.bar)}
          style={{ width: `${pct}%` }}
        />
      </div>
      {showLabel && (
        <span className={classNames("w-9 shrink-0 text-right text-xs font-semibold tabular-nums", tone.text)}>
          {pct}%
        </span>
      )}
    </div>
  );
}

/** Circular confidence gauge for the detail header. */
export function ConfidenceGauge({ confidence, size = 56 }: { confidence: number; size?: number }) {
  const pct = confidencePct(confidence);
  const tone = confidenceTone(confidence);
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  const stroke =
    tone.bar === "bg-brand-500" ? "#10b981" : tone.bar === "bg-amber-400" ? "#fbbf24" : "#fb7185";
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e2e8f0" strokeWidth={6} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={stroke}
          strokeWidth={6}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c - (pct / 100) * c}
          className="transition-all duration-500"
        />
      </svg>
      <span className="absolute text-xs font-bold tabular-nums text-slate-700">{pct}</span>
    </div>
  );
}

/** A small dot + count, used for error/warning tallies. */
export function CountPill({
  tone,
  count,
  label,
}: {
  tone: Severity | "neutral" | "good";
  count: number;
  label?: string;
}) {
  const cls =
    tone === "error"
      ? "bg-rose-50 text-rose-700 ring-rose-200"
      : tone === "warning"
        ? "bg-amber-50 text-amber-700 ring-amber-200"
        : tone === "good"
          ? "bg-brand-50 text-brand-700 ring-brand-200"
          : "bg-slate-100 text-slate-600 ring-slate-200";
  return (
    <span className={classNames("chip ring-1 ring-inset", cls)}>
      <span className="font-semibold tabular-nums">{count}</span>
      {label}
    </span>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={classNames("h-4 w-4 animate-spin", className)} />;
}

export function LoadingBlock({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-500">
      <Spinner /> {label}
    </div>
  );
}

export function ErrorBlock({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-rose-200 bg-rose-50/60 px-6 py-12 text-center">
      <AlertCircle className="h-7 w-7 text-rose-500" />
      <p className="max-w-md text-sm text-rose-700">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="btn-secondary">
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  hint,
  action,
}: {
  icon?: ReactNode;
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-slate-300 bg-white/50 px-6 py-14 text-center">
      <div className="text-slate-300">{icon ?? <Inbox className="h-8 w-8" />}</div>
      <p className="text-sm font-medium text-slate-700">{title}</p>
      {hint && <p className="max-w-sm text-sm text-slate-500">{hint}</p>}
      {action}
    </div>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={classNames("card", className)}>{children}</div>;
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">{children}</h3>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "error" | "warning" | "good" | "neutral";
}) {
  const valueColor =
    tone === "error"
      ? "text-rose-600"
      : tone === "warning"
        ? "text-amber-600"
        : tone === "good"
          ? "text-brand-600"
          : "text-slate-800";
  return (
    <div className="card px-4 py-3">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</div>
      <div className={classNames("mt-1 text-2xl font-bold tabular-nums", valueColor)}>{value}</div>
      {hint && <div className="text-xs text-slate-400">{hint}</div>}
    </div>
  );
}

/**
 * Compact one-line summary of a field's worst issue — handy in lists.
 * Returns a clean badge when there are no flags.
 */
export function FieldFlagSummary({ field }: { field: Field }) {
  const worst = worstSeverity(field.flags);
  if (!worst) {
    // No issue found: distinguish a value that's within margin from a field we
    // simply have no data for (blank) and couldn't assess.
    const blank = !`${field.value ?? field.value_raw ?? ""}`.trim();
    return blank ? (
      <span className="chip bg-slate-100 text-slate-500 ring-1 ring-inset ring-slate-200">
        unknown · no data
      </span>
    ) : (
      <span className="chip bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-200">
        within margin
      </span>
    );
  }
  const topByWorst = field.flags.filter((f) => f.severity === worst);
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <SeverityBadge severity={worst} />
      <span className="text-xs text-slate-500">
        {topByWorst.length} {worst}
        {topByWorst.length > 1 ? "s" : ""}
      </span>
    </div>
  );
}
