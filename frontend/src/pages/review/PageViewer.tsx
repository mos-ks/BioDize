// "Locate on page" panel. Tries the real scanned page image; if it 404s (the
// offline stub renders none) or there is no bbox, it falls back to a schematic
// A4 page so the reviewer ALWAYS sees where the value sits on the page.

import { useEffect, useState } from "react";
import { ImageOff, MapPin, ScanSearch } from "lucide-react";
import { api } from "../../api/client";
import type { BBox, Field } from "../../api/types";
import { classNames, fieldDisplayValue } from "../../lib/ui";

/** Convert a normalized [x0,y0,x1,y1] box into CSS percentage rect props. */
function rectFromBBox(bbox: BBox) {
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

function HighlightBox({ field, accent }: { field: Field; accent: "rose" | "brand" }) {
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

/** Faint horizontal rules to evoke a handwritten-form page. */
function SchematicPaper() {
  return (
    <div className="absolute inset-0 overflow-hidden rounded-lg bg-gradient-to-b from-white to-slate-50">
      <div className="absolute inset-x-4 top-4 h-3 rounded bg-slate-100" />
      <div className="absolute inset-x-4 top-4 mt-1 flex flex-col gap-[7%] pt-[10%]">
        {Array.from({ length: 11 }).map((_, i) => (
          <div key={i} className="h-px w-full bg-slate-200/80" />
        ))}
      </div>
    </div>
  );
}

export default function PageViewer({ field }: { field: Field }) {
  const [imgState, setImgState] = useState<"loading" | "ok" | "error">("loading");
  const src = api.pageImageUrl(field.document_id, field.page_no);
  const hasBox = !!field.bbox;
  const accent: "rose" | "brand" =
    field.flags.some((f) => f.severity === "error") ? "rose" : "brand";

  // Reset image probing whenever the page changes.
  useEffect(() => {
    setImgState("loading");
  }, [src]);

  const showSchematic = imgState !== "ok";

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400">
          <ScanSearch className="h-3.5 w-3.5" /> Page {field.page_no}
        </div>
        {showSchematic && imgState === "error" && (
          <span className="chip bg-slate-100 text-slate-500 ring-1 ring-inset ring-slate-200">
            <ImageOff className="h-3.5 w-3.5" /> schematic placeholder
          </span>
        )}
      </div>

      <div className="relative mx-auto w-full max-w-[320px]">
        <div
          className="relative w-full overflow-hidden rounded-lg border border-slate-200 bg-white shadow-card"
          style={{ aspectRatio: "1 / 1.414" }}
        >
          {/* Real image (hidden until it loads; probes onError to fall back). */}
          {/* eslint-disable-next-line jsx-a11y/img-redundant-alt */}
          <img
            src={src}
            alt={`Scanned page ${field.page_no}`}
            className={classNames(
              "absolute inset-0 h-full w-full object-contain",
              imgState === "ok" ? "opacity-100" : "opacity-0",
            )}
            onLoad={() => setImgState("ok")}
            onError={() => setImgState("error")}
            draggable={false}
          />

          {showSchematic && <SchematicPaper />}

          {hasBox ? (
            <HighlightBox field={field} accent={accent} />
          ) : (
            <div className="absolute inset-0 grid place-items-center p-4">
              <div className="rounded-lg border border-dashed border-slate-300 bg-white/70 px-3 py-2 text-center text-xs text-slate-400">
                No location available for this field.
              </div>
            </div>
          )}
        </div>

        <p className="mt-2 text-center text-[11px] text-slate-400">
          {showSchematic
            ? hasBox
              ? "Page image unavailable — schematic shows the field's position."
              : "Page image unavailable."
            : "Highlighted region marks the extracted value."}
        </p>
      </div>
    </div>
  );
}
