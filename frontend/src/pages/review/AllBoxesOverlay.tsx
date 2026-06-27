// Overlay that drops a location PIN on EVERY extracted field on the current page,
// so a reviewer can gauge completeness at a glance (what the pipeline caught,
// and — by absence — what it might have missed). We use pins, not boxes: the
// box edges were never reliable, but a pin just points at the spot.
//
// Pins are color-coded by the field's worst flag severity (error → rose,
// warning → amber, otherwise clean → emerald). The field currently under review
// is enlarged + ringed so the reviewer keeps their place. Hovering a pin reveals
// a lightweight label with the field's label + display value.
//
// Positioned with the same normalized-bbox-center logic as HighlightBox, over
// the same image wrapper, so it aligns in both the inline viewer and the lightbox.

import { MapPin } from "lucide-react";
import type { Field } from "../../api/types";
import { classNames, fieldDisplayValue } from "../../lib/ui";
import { bboxCenter } from "./HighlightBox";

type Severity = "error" | "warning" | "clean";

function fieldSeverity(field: Field): Severity {
  if (field.flags.some((f) => f.severity === "error")) return "error";
  if (field.flags.some((f) => f.severity === "warning")) return "warning";
  return "clean";
}

/** Pin fill/stroke + hover-label classes per severity. */
const TONE: Record<Severity, { pin: string; label: string }> = {
  error: { pin: "fill-rose-500 text-rose-700", label: "bg-rose-600" },
  warning: { pin: "fill-amber-400 text-amber-700", label: "bg-amber-600" },
  clean: { pin: "fill-emerald-500 text-emerald-700", label: "bg-emerald-600" },
};

export function AllBoxesOverlay({
  fields,
  currentFieldId,
  onSelect,
}: {
  fields: Field[];
  currentFieldId: string;
  /** When given, each pin is clickable and selects its field. */
  onSelect?: (id: string) => void;
}) {
  const boxed = fields.filter((f) => !!f.bbox);
  if (boxed.length === 0) return null;

  return (
    <div className="pointer-events-none absolute inset-0 animate-fade-in">
      {boxed.map((f) => {
        const pos = bboxCenter(f.bbox!);
        const tone = TONE[fieldSeverity(f)];
        const isCurrent = f.id === currentFieldId;
        return (
          <div
            key={f.id}
            // pointer-events re-enabled per pin so click/hover work while the
            // wrapper stays click-through to the image beneath.
            onClick={onSelect ? () => onSelect(f.id) : undefined}
            role={onSelect ? "button" : undefined}
            // Anchored at the value center; tip of the pin lands on the point.
            className={classNames(
              "group/box pointer-events-auto absolute z-10 flex -translate-x-1/2 -translate-y-full flex-col items-center",
              onSelect && "cursor-pointer",
              isCurrent && "z-20",
            )}
            style={pos}
          >
            {/* Lightweight hover label — label + display value. */}
            <span
              className={classNames(
                "pointer-events-none z-20 mb-0.5 hidden max-w-[200px] items-center gap-1 truncate rounded-md px-1.5 py-0.5 text-[11px] font-semibold text-white shadow-sm group-hover/box:inline-flex",
                tone.label,
              )}
            >
              <span className="truncate">
                {f.label_raw ? `${f.label_raw}: ` : ""}
                {fieldDisplayValue(f.value, f.value_raw)}
              </span>
            </span>
            <MapPin
              className={classNames(
                "drop-shadow-[0_1px_1px_rgba(0,0,0,0.35)] transition-transform group-hover/box:scale-110",
                tone.pin,
                isCurrent ? "h-7 w-7" : "h-5 w-5",
              )}
              strokeWidth={2.25}
            />
          </div>
        );
      })}
    </div>
  );
}

/** Count of fields with a drawable location (for the count chip). */
export function countBoxed(fields: Field[]): number {
  return fields.filter((f) => !!f.bbox).length;
}
