// Full-screen zoomable viewer for the scanned page. Opened from PageViewer when
// the real page image loaded successfully. Shows the same image much larger,
// with a scaled highlight-box overlay, zoom controls (buttons + Ctrl/⌘-scroll),
// and the show/hide-overlay toggle mirrored from the parent.

import { useEffect, useRef } from "react";
import { Boxes, Eye, EyeOff, X, ZoomIn, ZoomOut } from "lucide-react";
import type { Field } from "../../api/types";
import { classNames } from "../../lib/ui";
import { HighlightBox } from "./HighlightBox";
import { AllBoxesOverlay, countBoxed } from "./AllBoxesOverlay";

const ZOOM_STEPS = [1, 1.5, 2, 3] as const;

export default function PageLightbox({
  field,
  src,
  accent,
  hasBox,
  showOverlay,
  onToggleOverlay,
  showAllBoxes,
  onToggleAllBoxes,
  pageFields,
  zoom,
  onZoomIn,
  onZoomOut,
  onClose,
}: {
  field: Field;
  src: string;
  accent: "rose" | "brand";
  hasBox: boolean;
  showOverlay: boolean;
  onToggleOverlay: () => void;
  showAllBoxes: boolean;
  onToggleAllBoxes: () => void;
  pageFields: Field[];
  zoom: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onClose: () => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Close on Escape; restore body scroll on unmount.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  // Ctrl/⌘ + wheel to zoom (without scrolling the page).
  function handleWheel(e: React.WheelEvent) {
    if (!(e.ctrlKey || e.metaKey)) return;
    e.preventDefault();
    if (e.deltaY < 0) onZoomIn();
    else onZoomOut();
  }

  const atMin = zoom <= ZOOM_STEPS[0];
  const atMax = zoom >= ZOOM_STEPS[ZOOM_STEPS.length - 1];

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Scanned page ${field.page_no}, enlarged`}
      className="fixed inset-0 z-50 flex animate-fade-in flex-col bg-slate-900/70 backdrop-blur-sm"
      onClick={onClose}
    >
      {/* Toolbar */}
      <div
        className="flex items-center justify-between gap-2 px-4 py-3 text-white"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-white/80">
          Page {field.page_no}
          {showAllBoxes && (
            <span className="inline-flex items-center gap-1 rounded-full bg-white/15 px-2 py-0.5 text-xs font-medium normal-case tracking-normal text-white">
              <span className="font-semibold tabular-nums">{countBoxed(pageFields)}</span>
              {countBoxed(pageFields) === 1 ? "field on page" : "fields on page"}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {hasBox && (
            <button
              type="button"
              onClick={onToggleOverlay}
              aria-label={showOverlay ? "Hide highlight overlay" : "Show highlight overlay"}
              aria-pressed={showOverlay}
              title={showOverlay ? "Hide highlight" : "Show highlight"}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 text-white transition-colors hover:bg-white/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/50"
            >
              {showOverlay ? <Eye className="h-5 w-5" /> : <EyeOff className="h-5 w-5" />}
            </button>
          )}
          <button
            type="button"
            onClick={onToggleAllBoxes}
            aria-label={showAllBoxes ? "Hide all fields on page" : "Show all fields on page"}
            aria-pressed={showAllBoxes}
            title={showAllBoxes ? "Hide all fields on page" : "Show all fields on page"}
            className={classNames(
              "inline-flex h-9 w-9 items-center justify-center rounded-lg transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-white/50",
              showAllBoxes ? "bg-white text-slate-800 hover:bg-white/90" : "bg-white/10 text-white hover:bg-white/20",
            )}
          >
            <Boxes className="h-5 w-5" />
          </button>
          <button
            type="button"
            onClick={onZoomOut}
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
            onClick={onZoomIn}
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
            aria-label="Close enlarged view"
            title="Close (Esc)"
            className="ml-1 inline-flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 text-white transition-colors hover:bg-white/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/50"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* Scrollable, zoomable image stage */}
      <div
        ref={scrollRef}
        className="flex min-h-0 flex-1 items-center justify-center overflow-auto p-4"
        onClick={onClose}
        onWheel={handleWheel}
      >
        <div
          className="relative origin-center transition-transform duration-150"
          style={{ transform: `scale(${zoom})` }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Wrapper sized to the image so the normalized bbox overlay aligns. */}
          <div className="relative inline-block">
            <img
              src={src}
              alt={`Scanned page ${field.page_no}`}
              className="block max-h-[78vh] w-auto max-w-[90vw] rounded-lg bg-white object-contain shadow-panel"
              draggable={false}
            />
            {showAllBoxes && <AllBoxesOverlay fields={pageFields} currentFieldId={field.id} />}
            {hasBox && showOverlay && <HighlightBox field={field} accent={accent} />}
          </div>
        </div>
      </div>

      <p className="select-none pb-3 text-center text-xs text-white/50" onClick={onClose}>
        Ctrl/⌘ + scroll to zoom · click outside or press Esc to close
      </p>
    </div>
  );
}
