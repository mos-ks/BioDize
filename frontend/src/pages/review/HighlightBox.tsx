// The colored highlight rectangle + value label pill that marks where a field's
// value sits on the page. Uses normalized 0..1 bbox coords as CSS percentages so
// it scales naturally over any sized image wrapper (inline crop or lightbox).

import { MapPin } from "lucide-react";
import type { BBox, Field } from "../../api/types";
import { classNames, fieldDisplayValue } from "../../lib/ui";

/** Convert a normalized [x0,y0,x1,y1] box into CSS percentage rect props. */
export function rectFromBBox(bbox: BBox) {
  const [x0, y0, x1, y1] = bbox;
  const left = Math.min(x0, x1);
  const top = Math.min(y0, y1);
  const width = Math.abs(x1 - x0);
  const height = Math.abs(y1 - y0);
  return {
    left: `${left * 100}%`,
    top: `${top * 100}%`,
    width: `${Math.max(width, 0.01) * 100}%`,
    height: `${Math.max(height, 0.01) * 100}%`,
  };
}

export function HighlightBox({ field, accent }: { field: Field; accent: "rose" | "brand" }) {
  if (!field.bbox) return null;
  const rect = rectFromBBox(field.bbox);
  const ring = accent === "rose" ? "ring-rose-500 bg-rose-500/10" : "ring-brand-500 bg-brand-500/10";
  const labelBg = accent === "rose" ? "bg-rose-600" : "bg-brand-600";
  return (
    <div
      className={classNames(
        "absolute rounded-[3px] shadow-[0_0_0_9999px_rgba(15,23,42,0.04)] ring-2 ring-inset",
        "animate-fade-in",
        ring,
      )}
      style={rect}
    >
      <span
        className={classNames(
          "absolute -top-6 left-0 inline-flex max-w-[180px] items-center gap-1 truncate rounded-md px-1.5 py-0.5 text-[11px] font-semibold text-white shadow-sm",
          labelBg,
        )}
      >
        <MapPin className="h-3 w-3 shrink-0" />
        {fieldDisplayValue(field.value, field.value_raw)}
      </span>
    </div>
  );
}
