// Queue grouped by PAGE: each page is a card showing its errors/warnings
// together (not one flat list), and a clean page shows a green check. Click a
// flagged field to review it; errored pages start expanded. Any page (clean or
// not) can be opened full-screen to eyeball the whole scan with every field's box
// overlaid — that's how you verify a clean page, rather than listing its fields.
//
// A compact error-type filter above the list narrows the queue to the flag
// categories the reviewer cares about (e.g. only "Missing" or "Calculation").

import { useMemo, useState } from "react";
import { CheckCircle2, ChevronDown, ChevronRight, FilterX, Maximize2 } from "lucide-react";
import { api } from "../../api/client";
import type { Field, FlagCategory } from "../../api/types";
import { categoryMeta, classNames, useApi } from "../../lib/ui";
import { EmptyState, ErrorBlock, LoadingBlock } from "../../components/atoms";
import FieldRow from "./FieldRow";
import PageBoxesModal from "./PageBoxesModal";

type PageGroup = {
  page: number;
  all: Field[];
  flagged: Field[];
  nErr: number;
  nWarn: number;
};

export default function PageGroupedQueue({
  documentId,
  selectedId,
  onSelect,
}: {
  documentId: string;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { data: fields, loading, error, reload } = useApi<Field[]>(
    () => api.listFields(documentId, {}),
    [documentId],
  );
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  // Selected flag categories to filter by; empty set means "all".
  const [active, setActive] = useState<Set<FlagCategory>>(new Set());
  // Page whose full-screen "all boxes" view is open (null = closed).
  const [viewer, setViewer] = useState<PageGroup | null>(null);

  // Distinct flag categories present across the document, for the filter chips.
  const categories: FlagCategory[] = useMemo(() => {
    const seen = new Set<FlagCategory>();
    for (const f of fields ?? []) for (const fl of f.flags) seen.add(fl.category);
    return Array.from(seen).sort((a, b) => categoryMeta(a).label.localeCompare(categoryMeta(b).label));
  }, [fields]);

  const groups: PageGroup[] = useMemo(() => {
    const m = new Map<number, Field[]>();
    for (const f of fields ?? []) {
      const arr = m.get(f.page_no);
      if (arr) arr.push(f);
      else m.set(f.page_no, [f]);
    }
    return Array.from(m.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([page, fs]) => {
        const flagged = fs.filter(
          (f) =>
            f.flags.length > 0 &&
            (active.size === 0 || f.flags.some((fl) => active.has(fl.category))),
        );
        const nErr = flagged.filter((f) => f.flags.some((fl) => fl.severity === "error")).length;
        return { page, all: fs, flagged, nErr, nWarn: flagged.length - nErr };
      });
  }, [fields, active]);

  function toggle(c: FlagCategory) {
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(c)) next.delete(c);
      else next.add(c);
      return next;
    });
  }

  if (loading) return <LoadingBlock label="Loading pages…" />;
  if (error) return <ErrorBlock message={error} onRetry={reload} />;
  if (groups.length === 0) return <EmptyState title="No fields" />;

  const filtering = active.size > 0;
  // When filtering, only pages with at least one matching flagged field are shown.
  const visible = filtering ? groups.filter((g) => g.flagged.length > 0) : groups;
  const totalErr = visible.reduce((n, g) => n + g.nErr, 0);
  const cleanPages = visible.filter((g) => g.flagged.length === 0).length;

  return (
    <div className="animate-fade-in space-y-2">
      {categories.length > 0 && (
        <div className="card flex flex-wrap items-center gap-1.5 p-2">
          <span className="px-1 text-xs font-medium text-slate-400">Type</span>
          {categories.map((c) => {
            const m = categoryMeta(c);
            const Icon = m.icon;
            const on = active.has(c);
            return (
              <button
                key={c}
                type="button"
                onClick={() => toggle(c)}
                aria-pressed={on}
                className={classNames(
                  "chip transition-colors",
                  on
                    ? "bg-brand-600 text-white ring-1 ring-inset ring-brand-600"
                    : "bg-slate-100 text-slate-600 ring-1 ring-inset ring-slate-200 hover:bg-slate-200",
                )}
              >
                <Icon className={classNames("h-3.5 w-3.5", on ? "text-white" : m.color)} />
                {m.label}
              </button>
            );
          })}
          {filtering && (
            <button
              type="button"
              onClick={() => setActive(new Set())}
              className="btn-ghost ml-auto shrink-0 px-2 py-1 text-xs"
              title="Show all types"
            >
              <FilterX className="h-3.5 w-3.5" /> All
            </button>
          )}
        </div>
      )}

      <p className="px-1 text-xs text-slate-400">
        {visible.length} page{visible.length !== 1 ? "s" : ""} ·{" "}
        <span className="font-semibold text-rose-500">{totalErr}</span> errors ·{" "}
        <span className="font-semibold text-emerald-600">{cleanPages}</span> clean
      </p>

      {visible.length === 0 ? (
        <EmptyState
          title="No fields match this type"
          hint="Try a different flag type or clear the filter."
          action={
            <button onClick={() => setActive(new Set())} className="btn-secondary text-xs">
              <FilterX className="h-3.5 w-3.5" /> Clear filter
            </button>
          }
        />
      ) : (
        visible.map((g) => {
          const clean = g.flagged.length === 0;
          // Only errored pages expand to a flagged-field list. Clean pages have
          // nothing to step through — "View page" shows the whole scan instead.
          const open = !clean && (expanded[g.page] ?? g.nErr > 0);
          return (
            <div key={g.page} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-card">
              <div className="flex items-center gap-1 px-3 py-2.5">
                <button
                  type="button"
                  onClick={() => (clean ? setViewer(g) : setExpanded((e) => ({ ...e, [g.page]: !open })))}
                  className="flex min-w-0 flex-1 items-center gap-2 text-left"
                  title={clean ? "View the whole page" : open ? "Collapse" : "Expand flagged fields"}
                >
                  {clean ? (
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
                  ) : open ? (
                    <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" />
                  ) : (
                    <ChevronRight className="h-4 w-4 shrink-0 text-slate-400" />
                  )}
                  <span className="text-sm font-semibold text-slate-700">Page {g.page}</span>
                  <span className="ml-auto flex items-center gap-1.5">
                    {clean ? (
                      <span className="text-xs font-medium text-emerald-600">
                        clean · {g.all.length} field{g.all.length !== 1 ? "s" : ""}
                      </span>
                    ) : (
                      <>
                        {g.nErr > 0 && (
                          <span className="rounded-full bg-rose-50 px-2 py-0.5 text-xs font-semibold text-rose-600 ring-1 ring-inset ring-rose-200">
                            {g.nErr} error{g.nErr !== 1 ? "s" : ""}
                          </span>
                        )}
                        {g.nWarn > 0 && (
                          <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-semibold text-amber-600 ring-1 ring-inset ring-amber-200">
                            {g.nWarn} warning{g.nWarn !== 1 ? "s" : ""}
                          </span>
                        )}
                      </>
                    )}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => setViewer(g)}
                  aria-label={`View whole page ${g.page} with all fields`}
                  title="View whole page — every field on the scan"
                  className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40"
                >
                  <Maximize2 className="h-4 w-4" />
                </button>
              </div>
              {open && (
                <div className="space-y-1.5 border-t border-slate-100 p-2">
                  {g.flagged.map((f) => (
                    <FieldRow key={f.id} field={f} active={f.id === selectedId} onSelect={onSelect} />
                  ))}
                </div>
              )}
            </div>
          );
        })
      )}

      {viewer && (
        <PageBoxesModal
          documentId={documentId}
          pageNo={viewer.page}
          fields={viewer.all}
          onClose={() => setViewer(null)}
        />
      )}
    </div>
  );
}
