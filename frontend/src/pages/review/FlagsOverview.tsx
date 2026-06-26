// Read-only flags dashboard for the left pane "Flags" tab. Groups every flag by
// category with an error/warning split bar.

import { api } from "../../api/client";
import type { Flag, FlagCategory } from "../../api/types";
import { categoryMeta, useApi } from "../../lib/ui";
import { EmptyState, ErrorBlock, LoadingBlock, SeverityBadge } from "../../components/atoms";
import { ShieldCheck } from "lucide-react";

interface Group {
  category: FlagCategory;
  errors: number;
  warnings: number;
  flags: Flag[];
}

function groupByCategory(flags: Flag[]): Group[] {
  const map = new Map<FlagCategory, Group>();
  for (const f of flags) {
    let g = map.get(f.category);
    if (!g) {
      g = { category: f.category, errors: 0, warnings: 0, flags: [] };
      map.set(f.category, g);
    }
    g.flags.push(f);
    if (f.severity === "error") g.errors += 1;
    else g.warnings += 1;
  }
  return Array.from(map.values()).sort(
    (a, b) => b.errors - a.errors || b.warnings - a.warnings || b.flags.length - a.flags.length,
  );
}

function SplitBar({ errors, warnings }: { errors: number; warnings: number }) {
  const total = Math.max(errors + warnings, 1);
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-slate-100">
      {errors > 0 && <div className="h-full bg-rose-400" style={{ width: `${(errors / total) * 100}%` }} />}
      {warnings > 0 && <div className="h-full bg-amber-400" style={{ width: `${(warnings / total) * 100}%` }} />}
    </div>
  );
}

export default function FlagsOverview({ documentId }: { documentId: string }) {
  const { data: flags, loading, error, reload } = useApi<Flag[]>(
    () => api.listFlags(documentId),
    [documentId],
  );

  if (loading) return <LoadingBlock label="Loading flags…" />;
  if (error) return <ErrorBlock message={error} onRetry={reload} />;
  if (!flags || flags.length === 0) {
    return (
      <EmptyState
        icon={<ShieldCheck className="h-8 w-8" />}
        title="No validation flags"
        hint="Every field passed validation cleanly."
      />
    );
  }

  const groups = groupByCategory(flags);
  const totalErrors = flags.filter((f) => f.severity === "error").length;
  const totalWarnings = flags.length - totalErrors;

  return (
    <div className="animate-fade-in space-y-3">
      <div className="flex items-center gap-2 px-1 text-xs text-slate-500">
        <span className="inline-flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-rose-400" /> {totalErrors} errors
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-amber-400" /> {totalWarnings} warnings
        </span>
        <span className="ml-auto text-slate-400">{groups.length} categories</span>
      </div>

      {groups.map((g) => {
        const m = categoryMeta(g.category);
        const Icon = m.icon;
        return (
          <div key={g.category} className="card p-3">
            <div className="flex items-center gap-2">
              <Icon className={`h-4 w-4 ${m.color}`} />
              <span className="text-sm font-semibold text-slate-700">{m.label}</span>
              <div className="ml-auto flex items-center gap-1.5 text-xs tabular-nums">
                {g.errors > 0 && <span className="font-semibold text-rose-600">{g.errors}E</span>}
                {g.warnings > 0 && <span className="font-semibold text-amber-600">{g.warnings}W</span>}
              </div>
            </div>
            <div className="mt-2">
              <SplitBar errors={g.errors} warnings={g.warnings} />
            </div>
            <ul className="mt-2.5 space-y-1.5">
              {g.flags.map((f) => (
                <li key={f.id} className="flex items-start gap-2 text-xs">
                  <SeverityBadge severity={f.severity} />
                  <div className="min-w-0">
                    <code className="font-mono text-[11px] text-slate-400">{f.code}</code>
                    <p className="text-slate-600">{f.message}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
