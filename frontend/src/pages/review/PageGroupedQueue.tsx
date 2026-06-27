// Queue grouped by PAGE: each page is a card showing its errors/warnings
// together (not one flat list), and a clean page shows a green check. Click a
// flagged field to review it. Errored pages start expanded; clean ones collapse.

import { useMemo, useState } from "react";
import { CheckCircle2, ChevronDown, ChevronRight } from "lucide-react";
import { api } from "../../api/client";
import type { Field } from "../../api/types";
import { classNames, useApi } from "../../lib/ui";
import { EmptyState, ErrorBlock, LoadingBlock } from "../../components/atoms";
import FieldRow from "./FieldRow";

type PageGroup = {
  page: number;
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
        const flagged = fs.filter((f) => f.flags.length > 0);
        const nErr = flagged.filter((f) => f.flags.some((fl) => fl.severity === "error")).length;
        return { page, flagged, nErr, nWarn: flagged.length - nErr };
      });
  }, [fields]);

  if (loading) return <LoadingBlock label="Loading pages…" />;
  if (error) return <ErrorBlock message={error} onRetry={reload} />;
  if (groups.length === 0) return <EmptyState title="No fields" />;

  const totalErr = groups.reduce((n, g) => n + g.nErr, 0);
  const cleanPages = groups.filter((g) => g.flagged.length === 0).length;

  return (
    <div className="animate-fade-in space-y-2">
      <p className="px-1 text-xs text-slate-400">
        {groups.length} pages · <span className="font-semibold text-rose-500">{totalErr}</span> errors ·{" "}
        <span className="font-semibold text-emerald-600">{cleanPages}</span> clean
      </p>
      {groups.map((g) => {
        const clean = g.flagged.length === 0;
        const open = clean ? false : expanded[g.page] ?? g.nErr > 0;
        return (
          <div key={g.page} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-card">
            <button
              type="button"
              onClick={() => !clean && setExpanded((e) => ({ ...e, [g.page]: !open }))}
              className={classNames(
                "flex w-full items-center gap-2 px-3 py-2.5 text-left transition-colors",
                clean ? "cursor-default" : "hover:bg-slate-50",
              )}
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
                  <span className="text-xs font-medium text-emerald-600">clean</span>
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
            {open && !clean && (
              <div className="space-y-1.5 border-t border-slate-100 p-2">
                {g.flagged.map((f) => (
                  <FieldRow key={f.id} field={f} active={f.id === selectedId} onSelect={onSelect} />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
