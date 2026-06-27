// "Extraction" tab: the raw model read of EVERY field, grouped by page, BEFORE
// any validation / problem-recognition. Shows the value and the READER's own
// per-field confidence (its legibility self-assessment) — no flags, no status
// coloring. This is the "what did the model actually read" view.
//
// Mirrors the Queue's collapsible page-card pattern: each page is an
// expand/collapse card whose header reads "Page N · X fields".

import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { api } from "../../api/client";
import type { Field } from "../../api/types";
import { classNames, useApi } from "../../lib/ui";
import { EmptyState, ErrorBlock, LoadingBlock } from "../../components/atoms";

/** Reader's own per-field confidence (legibility) — NOT the post-validation
 *  uncertainty score, which a flag would drag down. This is the pre-recognition
 *  signal the user asked to see. */
function readerConfidence(f: Field): number {
  if (f.reads && f.reads.length > 0) return Math.min(...f.reads.map((r) => r.confidence));
  return f.confidence;
}

function confColor(c: number): string {
  if (c >= 0.85) return "bg-emerald-500";
  if (c >= 0.6) return "bg-amber-500";
  return "bg-rose-500";
}

export default function ExtractionList({
  documentId,
  activeId,
  onSelect,
}: {
  documentId: string;
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  const { data: fields, loading, error, reload } = useApi<Field[]>(
    () => api.listFields(documentId, {}),
    [documentId],
  );
  const [collapsed, setCollapsed] = useState<Record<number, boolean>>({});

  const byPage = useMemo(() => {
    const m = new Map<number, Field[]>();
    for (const f of fields ?? []) {
      const arr = m.get(f.page_no) ?? [];
      arr.push(f);
      m.set(f.page_no, arr);
    }
    return Array.from(m.entries()).sort((a, b) => a[0] - b[0]);
  }, [fields]);

  if (loading) return <LoadingBlock label="Loading extraction…" />;
  if (error) return <ErrorBlock message={error} onRetry={reload} />;
  if (!fields || fields.length === 0) return <EmptyState title="No fields extracted" />;

  return (
    <div className="animate-fade-in space-y-2">
      <p className="px-1 text-xs text-slate-400">
        Raw model read of {fields.length} fields — value + reader confidence, before any validation.
      </p>
      {byPage.map(([page, pageFields]) => {
        const open = !(collapsed[page] ?? false);
        return (
          <div key={page} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-card">
            <button
              type="button"
              onClick={() => setCollapsed((c) => ({ ...c, [page]: open }))}
              className="flex w-full items-center gap-2 px-3 py-2.5 text-left transition-colors hover:bg-slate-50"
            >
              {open ? (
                <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" />
              ) : (
                <ChevronRight className="h-4 w-4 shrink-0 text-slate-400" />
              )}
              <span className="text-sm font-semibold text-slate-700">Page {page}</span>
              <span className="ml-auto text-xs font-medium text-slate-400 tabular-nums">
                {pageFields.length} field{pageFields.length !== 1 ? "s" : ""}
              </span>
            </button>
            {open && (
              <div className="space-y-1.5 border-t border-slate-100 p-2">
                {pageFields.map((f) => {
                  const c = readerConfidence(f);
                  const val = (f.value_raw ?? f.value ?? "").trim();
                  return (
                    <button
                      key={f.id}
                      onClick={() => onSelect(f.id)}
                      className={classNames(
                        "flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left transition-colors",
                        f.id === activeId
                          ? "border-brand-300 bg-brand-50"
                          : "border-slate-200 bg-white hover:bg-slate-50",
                      )}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-xs text-slate-500">{f.label_raw || f.role || "—"}</div>
                        <div className="truncate text-sm font-medium text-slate-800">
                          {val ? val : <span className="italic text-slate-400">(blank)</span>}
                          {f.unit ? <span className="ml-1 text-xs font-normal text-slate-400">{f.unit}</span> : null}
                        </div>
                      </div>
                      <div className="flex w-16 shrink-0 flex-col items-end gap-1">
                        <span className="text-xs font-semibold tabular-nums text-slate-600">
                          {Math.round(c * 100)}%
                        </span>
                        <span className="block h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                          <span
                            className={classNames("block h-full rounded-full", confColor(c))}
                            style={{ width: `${Math.round(c * 100)}%` }}
                          />
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
