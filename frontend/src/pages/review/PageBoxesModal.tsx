// Full-page "show everything" view: the scanned page with EVERY extracted field's
// box overlaid (hover a box to read its label + value). Opened from the queue so a
// reviewer can eyeball a whole page at once — especially a clean one — instead of
// stepping through it field by field.

import { useEffect, useState } from "react";
import { ImageOff, X, ZoomIn, ZoomOut } from "lucide-react";
import { api } from "../../api/client";
import type { Field } from "../../api/types";
import { AllBoxesOverlay, countBoxed } from "./AllBoxesOverlay";

const ZOOM_STEPS = [1, 1.5, 2, 3];

export default function PageBoxesModal({
  documentId,
  pageNo,
  fields,
  onClose,
}: {
  documentId: string;
  pageNo: number;
  fields: Field[];
  onClose: () => void;
}) {
  const [zoom, setZoom] = useState(1);
  const [imgError, setImgError] = useState(false);
  const src = api.pageImageUrl(documentId, pageNo);

  // Close on Escape; lock body scroll while open.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  function handleWheel(e: React.WheelEvent) {
    if (!(e.ctrlKey || e.metaKey)) return;
    e.preventDefault();
    if (e.deltaY < 0) setZoom((z) => ZOOM_STEPS.find((s) => s > z) ?? z);
    else setZoom((z) => [...ZOOM_STEPS].reverse().find((s) => s < z) ?? z);
  }

  const atMin = zoom <= ZOOM_STEPS[0];
  const atMax = zoom >= ZOOM_STEPS[ZOOM_STEPS.length - 1];
  const boxCount = countBoxed(fields);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Page ${pageNo}, all fields`}
      className="fixed inset-0 z-50 flex animate-fade-in flex-col bg-slate-900/70 backdrop-blur-sm"
      onClick={onClose}
    >
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-2 px-4 py-3 text-white" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-white/80">
          Page {pageNo}
          <span className="inline-flex items-center gap-1 rounded-full bg-white/15 px-2 py-0.5 text-xs font-medium normal-case tracking-normal text-white">
            <span className="font-semibold tabular-nums">{boxCount}</span>
            {boxCount === 1 ? "field" : "fields"}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setZoom((z) => [...ZOOM_STEPS].reverse().find((s) => s < z) ?? z)}
            disabled={atMin}
            aria-label="Zoom out"
            title="Zoom out"
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 text-white transition-colors hover:bg-white/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ZoomOut className="h-5 w-5" />
          </button>
          <span className="w-12 select-none text-center text-sm font-semibold tabular-nums text-white/80">
            {Math.round(zoom * 100)}%
          </span>
          <button
            type="button"
            onClick={() => setZoom((z) => ZOOM_STEPS.find((s) => s > z) ?? z)}
            disabled={atMax}
            aria-label="Zoom in"
            title="Zoom in"
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 text-white transition-colors hover:bg-white/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ZoomIn className="h-5 w-5" />
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close page view"
            title="Close (Esc)"
            className="ml-1 inline-flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 text-white transition-colors hover:bg-white/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/50"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* Scrollable, zoomable image stage */}
      <div
        className="flex min-h-0 flex-1 items-center justify-center overflow-auto p-4"
        onClick={onClose}
        onWheel={handleWheel}
      >
        <div
          className="relative origin-center transition-transform duration-150"
          style={{ transform: `scale(${zoom})` }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="relative inline-block">
            {imgError ? (
              <div className="grid aspect-[1/1.414] h-[78vh] place-items-center rounded-lg bg-white text-slate-400">
                <span className="inline-flex items-center gap-2 text-sm">
                  <ImageOff className="h-5 w-5" /> Page image unavailable
                </span>
              </div>
            ) : (
              <img
                src={src}
                alt={`Scanned page ${pageNo}`}
                className="block max-h-[78vh] w-auto max-w-[90vw] rounded-lg bg-white object-contain shadow-panel"
                draggable={false}
                onError={() => setImgError(true)}
              />
            )}
            {!imgError && <AllBoxesOverlay fields={fields} currentFieldId="" />}
          </div>
        </div>
      </div>

      <p className="select-none pb-3 text-center text-xs text-white/50" onClick={onClose}>
        Hover a box to read its value · Ctrl/⌘ + scroll to zoom · click outside or press Esc to close
      </p>
    </div>
  );
}
