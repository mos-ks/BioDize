// Right-pane detail + the core review interaction (confirm / correct).

import { useEffect, useState } from "react";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  Pencil,
  ShieldCheck,
  X,
} from "lucide-react";
import { api } from "../../api/client";
import type { Field } from "../../api/types";
import {
  classNames,
  confidenceTone,
  fieldDisplayValue,
  roleIcon,
  roleLabel,
  useApi,
  useAsyncAction,
} from "../../lib/ui";
import {
  CategoryChip,
  ConfidenceGauge,
  ErrorBlock,
  LoadingBlock,
  SectionLabel,
  SeverityBadge,
  StatusBadge,
} from "../../components/atoms";
import PageViewer from "./PageViewer";
import PipelineTrace from "./PipelineTrace";
import OutlierDistribution from "./OutlierDistribution";

function FlagRow({ flag }: { flag: Field["flags"][number] }) {
  const isError = flag.severity === "error";
  const hasCompare = flag.expected != null || flag.actual != null;
  return (
    <li
      className={classNames(
        "rounded-lg border-l-4 bg-white p-3 shadow-card",
        isError ? "border-l-rose-400" : "border-l-amber-400",
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <SeverityBadge severity={flag.severity} />
        <CategoryChip category={flag.category} />
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-500">
          {flag.code}
        </code>
      </div>
      <p className="mt-1.5 text-sm text-slate-700">{flag.message}</p>
      {hasCompare && (
        <div className="mt-2 flex flex-wrap gap-2 text-xs">
          {flag.expected != null && (
            <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-1 text-emerald-700 ring-1 ring-inset ring-emerald-200">
              <span className="font-medium uppercase tracking-wide text-emerald-500/80">expected</span>
              <span className="font-mono tabular-nums">{flag.expected}</span>
            </span>
          )}
          {flag.actual != null && (
            <span
              className={classNames(
                "inline-flex items-center gap-1 rounded-md px-2 py-1 ring-1 ring-inset",
                isError
                  ? "bg-rose-50 text-rose-700 ring-rose-200"
                  : "bg-amber-50 text-amber-700 ring-amber-200",
              )}
            >
              <span className="font-medium uppercase tracking-wide opacity-70">actual</span>
              <span className="font-mono tabular-nums">{flag.actual}</span>
            </span>
          )}
        </div>
      )}
    </li>
  );
}

export default function FieldDetail({
  fieldId,
  onResolved,
  hasNext,
  onSkipNext,
}: {
  fieldId: string;
  /** Called after a successful confirm/correct so the parent can refresh + advance. */
  onResolved: (updated: Field) => void;
  hasNext: boolean;
  onSkipNext: () => void;
}) {
  const { data: field, loading, error, reload } = useApi<Field>(
    () => api.getField(fieldId),
    [fieldId],
  );

  const confirmAction = useAsyncAction((id: string) =>
    api.patchField(id, { action: "confirm", actor: "reviewer" }),
  );
  const correctAction = useAsyncAction((id: string, value: string, reason: string) =>
    api.patchField(id, {
      action: "correct",
      value,
      reason: reason.trim() ? reason.trim() : null,
      actor: "reviewer",
    }),
  );

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [reason, setReason] = useState("");
  const [justResolved, setJustResolved] = useState<null | "confirmed" | "corrected">(null);

  // Reset transient UI whenever a different field loads.
  useEffect(() => {
    setEditing(false);
    setReason("");
    setJustResolved(null);
  }, [fieldId]);

  useEffect(() => {
    if (field) setDraft(field.value ?? field.value_raw ?? "");
  }, [field]);

  if (loading) return <LoadingBlock label="Loading field…" />;
  if (error || !field)
    return <ErrorBlock message={error ?? "Field not found."} onRetry={reload} />;

  const Icon = roleIcon(field.role);
  const tone = confidenceTone(field.confidence);
  const busy = confirmAction.pending || correctAction.pending;
  const actionError = confirmAction.error || correctAction.error;

  async function handleConfirm() {
    const updated = await confirmAction.run(field!.id);
    if (updated) {
      setJustResolved("confirmed");
      onResolved(updated);
    }
  }

  async function handleSaveCorrection() {
    const updated = await correctAction.run(field!.id, draft, reason);
    if (updated) {
      setEditing(false);
      setJustResolved("corrected");
      onResolved(updated);
    }
  }

  return (
    <div className="animate-slide-up space-y-4">
      {/* a) Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-700">
            <Icon className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <h2 className="truncate text-lg font-bold text-slate-800">{roleLabel(field.role)}</h2>
            {field.label_raw && (
              <p className="truncate text-sm text-slate-400">{field.label_raw}</p>
            )}
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              <StatusBadge status={field.status} />
              {field.chapter && (
                <span className="chip bg-slate-100 text-slate-500 ring-1 ring-inset ring-slate-200">
                  ch. {field.chapter}
                </span>
              )}
              <span className="chip bg-slate-100 text-slate-500 ring-1 ring-inset ring-slate-200">
                page {field.page_no}
              </span>
            </div>
          </div>
        </div>
        <div className="shrink-0 text-center">
          <ConfidenceGauge confidence={field.confidence} size={60} />
          <div className={classNames("text-[11px] font-semibold", tone.text)}>{tone.label}</div>
        </div>
      </div>

      {justResolved && (
        <div className="flex animate-fade-in items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-700 ring-1 ring-inset ring-emerald-200">
          <CheckCircle2 className="h-4 w-4" />
          {justResolved === "confirmed" ? "Value confirmed." : "Correction saved."}
          {hasNext && (
            <button onClick={onSkipNext} className="btn-ghost ml-auto px-2 py-1 text-xs text-emerald-700">
              Next <ArrowRight className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(360px,46%)]">
        {/* LEFT: value + validation, stacked so the column is filled (no dead space) */}
        <div className="order-2 space-y-4 lg:order-1">
          <div className="card flex flex-wrap items-baseline gap-x-3 gap-y-1 p-4">
            <SectionLabel>Extracted value</SectionLabel>
            <div className="flex w-full items-baseline gap-2">
              <span className="font-mono text-3xl font-bold tabular-nums text-slate-900">
                {field.value_raw?.trim() ? field.value_raw : fieldDisplayValue(field.value, field.value_raw)}
              </span>
              {field.unit && <span className="text-base font-medium text-slate-400">{field.unit}</span>}
              {field.nks != null && (
                <span className="ml-auto text-xs text-slate-400">
                  {field.nks} dp
                </span>
              )}
            </div>
          </div>

          {/* Validation */}
          <div>
            <SectionLabel>
              Validation {field.flags.length > 0 ? `· ${field.flags.length}` : ""}
            </SectionLabel>
            {field.flags.length === 0 ? (
              <div className="mt-2 flex items-center gap-2 rounded-lg bg-brand-50/60 px-3 py-3 text-sm font-medium text-brand-700 ring-1 ring-inset ring-brand-200">
                <ShieldCheck className="h-4 w-4" /> No validation issues on this field.
              </div>
            ) : (
              <ul className="mt-2 space-y-2">
                {field.flags.map((f) => (
                  <FlagRow key={f.id} flag={f} />
                ))}
              </ul>
            )}
          </div>

          {/* Anomaly distribution — only when this value is a statistical outlier */}
          {field.flags.some((fl) => fl.code === "STAT_OUTLIER") && (
            <OutlierDistribution field={field} />
          )}
          {/* Pipeline trace + Confirm/Correct actions live under validation here */}
          <PipelineTrace field={field} />

      {/* e) Actions */}
      <div className="card p-4">
        {actionError && (
          <div className="mb-3 flex items-center gap-2 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 ring-1 ring-inset ring-rose-200">
            <X className="h-4 w-4 shrink-0" /> {actionError}
          </div>
        )}

        {!editing ? (
          <div className="flex flex-wrap items-center gap-2">
            <button onClick={handleConfirm} disabled={busy} className="btn-primary">
              <Check className="h-4 w-4" /> Confirm value
            </button>
            <button
              onClick={() => {
                setDraft(field.value ?? field.value_raw ?? "");
                setEditing(true);
              }}
              disabled={busy}
              className="btn-secondary"
            >
              <Pencil className="h-4 w-4" /> Correct…
            </button>
            <span className="ml-auto text-xs text-slate-400">
              Confirm accepts the proposed value as-is.
            </span>
          </div>
        ) : (
          <div className="animate-fade-in space-y-3">
            <div>
              <label className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Corrected value
              </label>
              <div className="mt-1 flex items-center gap-2">
                <input
                  className="input font-mono"
                  value={draft}
                  autoFocus
                  spellCheck={false}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && draft.trim() && !busy) handleSaveCorrection();
                    if (e.key === "Escape") setEditing(false);
                  }}
                  placeholder="Enter the correct value"
                />
                {field.unit && <span className="shrink-0 text-sm text-slate-400">{field.unit}</span>}
              </div>
            </div>
            <div>
              <label className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Reason <span className="font-normal normal-case text-slate-300">(optional, for the audit trail)</span>
              </label>
              <input
                className="input mt-1"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. misread digit, clarified with operator…"
              />
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleSaveCorrection}
                disabled={busy || !draft.trim()}
                className="btn-primary"
              >
                <Check className="h-4 w-4" /> Save correction
              </button>
              <button onClick={() => setEditing(false)} disabled={busy} className="btn-ghost">
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
        </div>

        {/* RIGHT: page viewer, hugs its own content */}
        <div className="card order-1 self-start p-4 lg:order-2">
          <PageViewer field={field} />
        </div>
      </div>
    </div>
  );
}
