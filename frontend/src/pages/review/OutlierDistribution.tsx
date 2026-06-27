// Shown for a field flagged STAT_OUTLIER: the distribution of all recorded values
// for this parameter (role), with a marker at where THIS value sits — so the
// reviewer sees instantly how far out of the pack it is.

import { useMemo } from "react";
import { api } from "../../api/client";
import type { Distribution, Field } from "../../api/types";
import { useApi } from "../../lib/ui";
import { LoadingBlock } from "../../components/atoms";
import { Histogram } from "../stats/Histogram";

function toNum(s: string | null | undefined): number | null {
  if (!s) return null;
  const n = parseFloat(String(s).replace(/\s/g, "").replace(",", "."));
  return Number.isFinite(n) ? n : null;
}

export default function OutlierDistribution({ field }: { field: Field }) {
  const role = field.role ?? "";
  const { data, loading } = useApi<Distribution>(() => api.getDistribution(role, 12), [role]);
  const value = useMemo(() => toNum(field.value ?? field.value_raw), [field]);

  if (!role) return null;
  if (loading) return <LoadingBlock label="Loading distribution…" />;
  if (!data || !data.histogram || data.histogram.length === 0) return null;

  const roleLabel = role.replace(/_/g, " ");
  return (
    <div className="card p-3">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          {roleLabel} distribution
        </span>
        <span className="text-[11px] tabular-nums text-slate-400">n={data.n}</span>
      </div>
      <Histogram bins={data.histogram} unit={field.unit} min={data.min} max={data.max} mark={value} />
      <p className="mt-1.5 text-[11px] text-slate-500">
        <span className="font-semibold text-rose-500">This value</span>
        {value != null ? ` (${value}${field.unit ? ` ${field.unit}` : ""})` : ""} vs {data.n} recorded{" "}
        {roleLabel} values
        {data.mean != null && data.std != null
          ? ` — mean ${data.mean.toFixed(1)} ± ${data.std.toFixed(1)}`
          : ""}
        .
      </p>
    </div>
  );
}
