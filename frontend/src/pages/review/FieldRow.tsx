// A selectable field row used in both the Queue and All-fields lists.

import type { Field } from "../../api/types";
import {
  classNames,
  fieldDisplayValue,
  roleIcon,
  roleLabel,
} from "../../lib/ui";
import { ConfidenceMeter, FieldFlagSummary } from "../../components/atoms";

export default function FieldRow({
  field,
  active,
  onSelect,
}: {
  field: Field;
  active: boolean;
  onSelect: (id: string) => void;
}) {
  const Icon = roleIcon(field.role);
  return (
    <button
      type="button"
      onClick={() => onSelect(field.id)}
      aria-current={active}
      className={classNames(
        "group w-full rounded-xl border bg-white px-3.5 py-3 text-left transition-all",
        "border-l-4 hover:border-slate-300 hover:shadow-card focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40",
        active
          ? "border-slate-200 border-l-brand-500 bg-brand-50/40 shadow-card ring-1 ring-brand-500/30"
          : "border-slate-200 border-l-transparent",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className={classNames(
              "grid h-7 w-7 shrink-0 place-items-center rounded-lg",
              active ? "bg-brand-100 text-brand-700" : "bg-slate-100 text-slate-500",
            )}
          >
            <Icon className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-slate-800">{roleLabel(field.role)}</div>
            {field.label_raw && (
              <div className="truncate text-xs text-slate-400" title={field.label_raw}>
                {field.label_raw}
              </div>
            )}
          </div>
        </div>
        <span className="chip shrink-0 bg-slate-100 text-slate-500 ring-1 ring-inset ring-slate-200">
          p.{field.page_no}
        </span>
      </div>

      <div className="mt-2 flex items-baseline gap-1.5">
        <span className="truncate font-mono text-base font-semibold tabular-nums text-slate-900">
          {fieldDisplayValue(field.value, field.value_raw)}
        </span>
        {field.unit && <span className="text-xs font-medium text-slate-400">{field.unit}</span>}
      </div>

      <div className="mt-2.5 flex items-center gap-3">
        <ConfidenceMeter confidence={field.confidence} className="max-w-[140px]" />
        <div className="ml-auto">
          <FieldFlagSummary field={field} />
        </div>
      </div>
    </button>
  );
}
