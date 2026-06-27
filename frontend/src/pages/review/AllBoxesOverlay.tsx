// Overlay that draws EVERY extracted field's bounding box on the current page,
// so a reviewer can gauge completeness at a glance (what the pipeline caught,
// and — by absence — what it might have missed).
//
// Boxes are color-coded by the field's worst flag severity (error → rose,
// warning → amber, otherwise clean → emerald/brand) with a thin ring + faint
// fill so dozens read clearly at once. The field currently under review is
// emphasized with a thicker ring so the reviewer keeps their place. Hovering a
// box reveals a lightweight label with the field's label + display value.
//
// Positioned with the same normalized-bbox → CSS % logic as HighlightBox, over
// the same image wrapper, so it aligns in both the inline viewer and the
// zoomable lightbox.

import type { Field } from "../../api/types";
import { classNames, fieldDisplayValue } from "../../lib/ui";
import { rectFromBBox } from "./HighlightBox";

type Severity = "error" | "warning" | "clean";

function fieldSeverity(field: Field): Severity {
  if (field.flags.some((f) => f.severity === "error")) return "error";
  if (field.flags.some((f) => f.severity === "warning")) return "warning";
  return "clean";
}

/** Ring + fill classes per severity (low-opacity so many overlap readably). */
const TONE: Record<Severity, { ring: string; fill: string; label: string }> = {
  error: { ring: "ring-rose-500", fill: "bg-rose-500/10", label: "bg-rose-600" },
  warning: { ring: "ring-amber-500", fill: "bg-amber-400/10", label: "bg-amber-600" },
  clean: { ring: "ring-emerald-500", fill: "bg-emerald-500/10", label: "bg-emerald-600" },
};

export function AllBoxesOverlay({
  fields,
  currentFieldId,
}: {
  fields: Field[];
  currentFieldId: string;
}) {
  const boxed = fields.filter((f) => !!f.bbox);
  if (boxed.length === 0) return null;

  return (
    <div className="pointer-events-none absolute inset-0 animate-fade-in">
      {boxed.map((f) => {
        const rect = rectFromBBox(f.bbox!);
        const tone = TONE[fieldSeverity(f)];
        const isCurrent = f.id === currentFieldId;
        return (
          <div
            key={f.id}
            // pointer-events re-enabled per box so the hover tooltip works while
            // the wrapper stays click-through to the image beneath.
            className={classNames(
              "group/box pointer-events-auto absolute rounded-[3px] ring-inset transition-shadow",
              tone.fill,
              tone.ring,
              isCurrent ? "z-10 ring-[3px] shadow-[0_0_0_2px_rgba(255,255,255,0.85)]" : "ring-1",
            )}
            style={rect}
          >
            {/* Lightweight hover label — label + display value. */}
            <span
              className={classNames(
                "pointer-events-none absolute -top-6 left-0 z-20 hidden max-w-[200px] items-center gap-1 truncate rounded-md px-1.5 py-0.5 text-[11px] font-semibold text-white shadow-sm group-hover/box:inline-flex",
                tone.label,
              )}
            >
              <span className="truncate">
                {f.label_raw ? `${f.label_raw}: ` : ""}
                {fieldDisplayValue(f.value, f.value_raw)}
              </span>
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** Count of fields with a drawable bbox (for the count chip). */
export function countBoxed(fields: Field[]): number {
  return fields.filter((f) => !!f.bbox).length;
}
