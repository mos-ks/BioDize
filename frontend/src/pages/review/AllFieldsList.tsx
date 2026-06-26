// "All fields" tab: a compact filter bar over api.listFields + the result list.

import { useMemo, useState } from "react";
import { FilterX, Search } from "lucide-react";
import { api } from "../../api/client";
import type {
  Field,
  FieldFilters,
  FieldStatus,
  FlagCategory,
  Severity,
} from "../../api/types";
import { CATEGORY_META, ROLE_LABELS, STATUS_META, useApi } from "../../lib/ui";
import { EmptyState, ErrorBlock, LoadingBlock } from "../../components/atoms";
import FieldRow from "./FieldRow";

const STATUS_OPTIONS = Object.keys(STATUS_META) as FieldStatus[];
const CATEGORY_OPTIONS = Object.keys(CATEGORY_META) as FlagCategory[];
const SEVERITY_OPTIONS: Severity[] = ["error", "warning"];

export default function AllFieldsList({
  documentId,
  activeId,
  onSelect,
}: {
  documentId: string;
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  const [status, setStatus] = useState<FieldStatus | "">("");
  const [severity, setSeverity] = useState<Severity | "">("");
  const [category, setCategory] = useState<FlagCategory | "">("");
  const [role, setRole] = useState<string>("");
  const [pageNo, setPageNo] = useState<string>("");

  const filters: FieldFilters = useMemo(() => {
    const f: FieldFilters = {};
    if (status) f.status = status;
    if (severity) f.severity = severity;
    if (category) f.category = category;
    if (role) f.role = role;
    const p = parseInt(pageNo, 10);
    if (!Number.isNaN(p)) f.page_no = p;
    return f;
  }, [status, severity, category, role, pageNo]);

  const filterKey = JSON.stringify(filters);
  const { data: fields, loading, error, reload } = useApi<Field[]>(
    () => api.listFields(documentId, filters),
    [documentId, filterKey],
  );

  const hasFilters = !!(status || severity || category || role || pageNo);
  const rolesPresent = useMemo(
    () => Array.from(new Set((fields ?? []).map((f) => f.role).filter(Boolean) as string[])).sort(),
    [fields],
  );

  function clearFilters() {
    setStatus("");
    setSeverity("");
    setCategory("");
    setRole("");
    setPageNo("");
  }

  return (
    <div className="space-y-3">
      {/* Filter bar */}
      <div className="card space-y-2 p-2.5">
        <div className="grid grid-cols-2 gap-2">
          <select className="input py-1.5 text-xs" value={status} onChange={(e) => setStatus(e.target.value as FieldStatus | "")}>
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {STATUS_META[s].label}
              </option>
            ))}
          </select>
          <select className="input py-1.5 text-xs" value={severity} onChange={(e) => setSeverity(e.target.value as Severity | "")}>
            <option value="">Any severity</option>
            {SEVERITY_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s === "error" ? "Errors" : "Warnings"}
              </option>
            ))}
          </select>
          <select className="input py-1.5 text-xs" value={category} onChange={(e) => setCategory(e.target.value as FlagCategory | "")}>
            <option value="">All categories</option>
            {CATEGORY_OPTIONS.map((c) => (
              <option key={c} value={c}>
                {CATEGORY_META[c].label}
              </option>
            ))}
          </select>
          <select className="input py-1.5 text-xs" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="">All roles</option>
            {/* Roles seen in the current result set, falling back to known labels. */}
            {(rolesPresent.length > 0 ? rolesPresent : Object.keys(ROLE_LABELS)).map((r) => (
              <option key={r} value={r}>
                {ROLE_LABELS[r] ?? r}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
            <input
              className="input py-1.5 pl-8 text-xs tabular-nums"
              type="number"
              min={1}
              inputMode="numeric"
              value={pageNo}
              onChange={(e) => setPageNo(e.target.value)}
              placeholder="Page no."
            />
          </div>
          <button
            onClick={clearFilters}
            disabled={!hasFilters}
            className="btn-ghost shrink-0 px-2.5 py-1.5 text-xs"
            title="Clear filters"
          >
            <FilterX className="h-3.5 w-3.5" /> Clear
          </button>
        </div>
      </div>

      {/* Results */}
      {loading ? (
        <LoadingBlock label="Loading fields…" />
      ) : error ? (
        <ErrorBlock message={error} onRetry={reload} />
      ) : !fields || fields.length === 0 ? (
        <EmptyState
          title={hasFilters ? "No fields match these filters" : "No fields"}
          hint={hasFilters ? "Try widening or clearing the filters." : undefined}
          action={
            hasFilters ? (
              <button onClick={clearFilters} className="btn-secondary text-xs">
                <FilterX className="h-3.5 w-3.5" /> Clear filters
              </button>
            ) : undefined
          }
        />
      ) : (
        <>
          <div className="px-1 text-xs text-slate-400">
            {fields.length} field{fields.length !== 1 ? "s" : ""}
          </div>
          <div className="space-y-2">
            {fields.map((f) => (
              <FieldRow key={f.id} field={f} active={f.id === activeId} onSelect={onSelect} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
