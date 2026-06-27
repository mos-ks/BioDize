// The little form shown after a reviewer drags a box on the PDF: label it and
// mark it error / warning / note, then it's saved as a HUMAN-labeled entry into
// the record and the review list (api.addAnnotation).

import { useState } from "react";
import { Check, X } from "lucide-react";
import { api } from "../../api/client";
import type { AnnotationInput, Field } from "../../api/types";
import { classNames, useAsyncAction } from "../../lib/ui";

type Sev = "error" | "warning" | "none";

export default function AnnotationForm({
  documentId,
  pageNo,
  bbox,
  onClose,
  onSaved,
}: {
  documentId: string;
  pageNo: number;
  bbox: number[];
  onClose: () => void;
  onSaved: (f: Field) => void;
}) {
  const [label, setLabel] = useState("");
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const [severity, setSeverity] = useState<Sev>("error");

  const save = useAsyncAction(async () => {
    const body: AnnotationInput = {
      page_no: pageNo,
      bbox,
      label: label.trim() || "Human annotation",
      value: value.trim() || undefined,
      note: note.trim() || undefined,
      severity: severity === "none" ? null : severity,
      actor: "reviewer",
    };
    const f = await api.addAnnotation(documentId, body);
    onSaved(f);
    onClose();
    return f;
  });

  const sevTone: Record<Sev, string> = {
    error: "bg-rose-600 text-white ring-rose-600",
    warning: "bg-amber-500 text-white ring-amber-500",
    none: "bg-slate-600 text-white ring-slate-600",
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/30 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className="mt-20 w-full max-w-md animate-slide-up rounded-2xl border border-slate-200 bg-white p-5 shadow-panel"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-slate-800">Add entry · page {pageNo}</h2>
          <button onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600">
            <X className="h-4 w-4" />
          </button>
        </div>
        <p className="mt-1 text-sm text-slate-500">
          Saved as a <span className="font-medium text-violet-700">human-labeled</span> entry on this box —
          it lands in the record and the review list.
        </p>

        <label className="mt-4 block text-xs font-semibold uppercase tracking-wide text-slate-400">Label</label>
        <input
          className="input mt-1"
          value={label}
          autoFocus
          onChange={(e) => setLabel(e.target.value)}
          placeholder="e.g. Missing signature"
        />

        <label className="mt-3 block text-xs font-semibold uppercase tracking-wide text-slate-400">Value (optional)</label>
        <input
          className="input mt-1"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="the correct / observed value"
        />

        <label className="mt-3 block text-xs font-semibold uppercase tracking-wide text-slate-400">Note (optional)</label>
        <textarea
          className="input mt-1"
          rows={2}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="why you flagged this"
        />

        <label className="mt-3 block text-xs font-semibold uppercase tracking-wide text-slate-400">Mark as</label>
        <div className="mt-1 flex gap-1.5">
          {(["error", "warning", "none"] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSeverity(s)}
              className={classNames(
                "chip capitalize ring-1 ring-inset transition-colors",
                severity === s ? sevTone[s] : "bg-slate-100 text-slate-600 ring-slate-200 hover:bg-slate-200",
              )}
            >
              {s === "none" ? "Note only" : s}
            </button>
          ))}
        </div>

        {save.error && <p className="mt-3 text-xs font-medium text-rose-600">{save.error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="btn-secondary">Cancel</button>
          <button onClick={() => save.run()} disabled={save.pending} className="btn-primary">
            <Check className="h-4 w-4" /> Save entry
          </button>
        </div>
      </div>
    </div>
  );
}
