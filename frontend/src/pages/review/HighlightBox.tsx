// A red location PIN that marks where a field's value sits on the page (we drop
// the bounding rectangle entirely — the box edges were never reliable, a pin just
// points at the spot). Uses normalized 0..1 bbox coords as CSS percentages so it
// scales naturally over any sized image wrapper (inline crop or lightbox).

import { MapPin } from "lucide-react";
import type { BBox, Field } from "../../api/types";
import { classNames } from "../../lib/ui";

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

/** The point a pin should drop on: the center of the (normalized) bbox. */
export function bboxCenter(bbox: BBox): { left: string; top: string } {
  const [x0, y0, x1, y1] = bbox;
  return { left: `${((x0 + x1) / 2) * 100}%`, top: `${((y0 + y1) / 2) * 100}%` };
}

export function HighlightBox({ field, accent }: { field: Field; accent: "rose" | "brand" }) {
  if (!field.bbox) return null;
  const pos = bboxCenter(field.bbox);
  const pin = accent === "rose" ? "fill-rose-500 text-rose-700" : "fill-brand-500 text-brand-700";
  return (
    // Anchored at the value's center; translated up+left so the pin's tip lands
    // exactly on the point. No label — the pin alone marks the spot.
    <div
      className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full animate-fade-in"
      style={pos}
    >
      <MapPin className={classNames("h-7 w-7 drop-shadow-[0_1px_1px_rgba(0,0,0,0.35)]", pin)} strokeWidth={2.25} />
    </div>
  );
}
