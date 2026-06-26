// Validation-flag dashboard for a single document.
// Per-category stacked bars (error=rose, warning=amber) + grouped flag list.

import { useMemo, useState } from "react";
import { ChevronDown, ShieldCheck } from "lucide-react";
import type { Flag, FlagCategory, Severity } from "../../api/types";
import { categoryMeta, classNames, severityMeta } from "../../lib/ui";
import { CategoryChip, EmptyState, SectionLabel, SeverityBadge, Stat } from "../../components/atoms";

interface CategoryRow {
  category: FlagCategory;
  error: number;
  warning: number;
  total: number;
  flags: Flag[];
}

function groupByCategory(flags: Flag[]): CategoryRow[] {
  const map = new Map<FlagCategory, CategoryRow>();
  for (const f of flags) {
    let row = map.get(f.category);
    if (!row) {
      row = { category: f.category, error: 0, warning: 0, total: 0, flags: [] };
      map.set(f.category, row);
    }
    row.flags.push(f);
    row.total += 1;
    if (f.severity === "error") row.error += 1;
    else row.warning += 1;
  }
  return [...map.values()].sort((a, b) => b.error - a.error || b.total - a.total);
}

function FlagItem({ flag }: { flag: Flag }) {
  const tint = severityMeta(flag.severity).tint;
  const border = severityMeta(flag.severity).border;
  return (
    <li
      className={classNames(
        "flex flex-col gap-1.5 rounded-lg border-l-2 px-3 py-2.5",
        tint,
        border,
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={flag.severity} />
        <code className="rounded bg-white/70 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-slate-600 ring-1 ring-inset ring-slate-200">
          {flag.code}
        </code>
      </div>
      <p className="text-sm leading-snug text-slate-700">{flag.message}</p>
      {(flag.expected != null || flag.actual != null) && (
        <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-slate-500">
          {flag.expected != null && (
            <span>
              <span className="text-slate-400">expected </span>
              <span className="font-medium tabular-nums text-slate-600">{flag.expected}</span>
            </span>
          )}
          {flag.actual != null && (
            <span>
              <span className="text-slate-400">actual </span>
              <span className="font-medium tabular-nums text-slate-600">{flag.actual}</span>
            </span>
          )}
        </div>
      )}
    </li>
  );
}

function CategorySection({ row, maxTotal }: { row: CategoryRow; maxTotal: number }) {
  const [open, setOpen] = useState(false);
  const meta = categoryMeta(row.category);
  const Icon = meta.icon;
  const errPct = (row.error / maxTotal) * 100;
  const warnPct = (row.warning / maxTotal) * 100;

  return (
    <div className="border-t border-slate-100 first:border-t-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 py-2.5 text-left transition-colors hover:bg-slate-50/70"
      >
        <span className="flex w-40 shrink-0 items-center gap-2">
          <Icon className={classNames("h-4 w-4 shrink-0", meta.color)} />
          <span className="truncate text-sm font-medium text-slate-700">{meta.label}</span>
        </span>

        <span className="flex h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100">
          {row.error > 0 && (
            <span
              className="h-full bg-rose-400"
              style={{ width: `${errPct}%` }}
              title={`${row.error} error${row.error > 1 ? "s" : ""}`}
            />
          )}
          {row.warning > 0 && (
            <span
              className="h-full bg-amber-400"
              style={{ width: `${warnPct}%` }}
              title={`${row.warning} warning${row.warning > 1 ? "s" : ""}`}
            />
          )}
        </span>

        <span className="flex w-24 shrink-0 items-center justify-end gap-2 text-xs tabular-nums">
          {row.error > 0 && <span className="font-semibold text-rose-600">{row.error}e</span>}
          {row.warning > 0 && <span className="font-semibold text-amber-600">{row.warning}w</span>}
          <ChevronDown
            className={classNames(
              "h-4 w-4 text-slate-300 transition-transform",
              open && "rotate-180",
            )}
          />
        </span>
      </button>

      {open && (
        <ul className="mb-2 ml-1 flex flex-col gap-1.5 pb-1 pl-6">
          {row.flags
            .slice()
            .sort((a, b) => (a.severity === b.severity ? 0 : a.severity === "error" ? -1 : 1))
            .map((f) => (
              <FlagItem key={f.id} flag={f} />
            ))}
        </ul>
      )}
    </div>
  );
}

export function FlagsDashboard({ flags }: { flags: Flag[] }) {
  const rows = useMemo(() => groupByCategory(flags), [flags]);
  const totals = useMemo(() => {
    let error = 0;
    let warning = 0;
    for (const f of flags) {
      if (f.severity === "error") error += 1;
      else warning += 1;
    }
    return { error, warning, total: flags.length };
  }, [flags]);

  if (flags.length === 0) {
    return (
      <EmptyState
        icon={<ShieldCheck className="h-8 w-8 text-brand-400" />}
        title="No validation flags"
        hint="Every field passed silently — nothing was provably wrong or suspicious in this document."
      />
    );
  }

  const maxTotal = Math.max(1, ...rows.map((r) => r.total));

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Total flags" value={totals.total} tone="neutral" />
        <Stat label="Errors" value={totals.error} tone="error" hint="must be resolved" />
        <Stat label="Warnings" value={totals.warning} tone="warning" hint="worth a glance" />
      </div>

      <div className="card p-4">
        <div className="mb-1 flex items-center justify-between">
          <SectionLabel>By category</SectionLabel>
          <div className="flex items-center gap-3 text-[11px] text-slate-400">
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-rose-400" /> error
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-amber-400" /> warning
            </span>
          </div>
        </div>
        <div>
          {rows.map((row) => (
            <CategorySection key={row.category} row={row} maxTotal={maxTotal} />
          ))}
        </div>
        <p className="mt-3 border-t border-slate-100 pt-2.5 text-[11px] text-slate-400">
          Click a category to read its flags. Severities:{" "}
          {(["error", "warning"] as Severity[]).map((s) => severityMeta(s).label).join(" · ")}.
        </p>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {rows.map((row) => (
          <CategoryChip key={row.category} category={row.category} />
        ))}
      </div>
    </div>
  );
}
