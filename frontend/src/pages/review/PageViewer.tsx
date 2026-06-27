// "Locate on page" panel. Tries the real scanned page image; if it 404s (the
// offline stub renders none) or there is no bbox, it falls back to a schematic
// A4 page so the reviewer ALWAYS sees where the value sits on the page.
//
// Reviewer controls (only meaningful when the field has a bbox / the real image
// loaded): toggle the highlight overlay on/off to inspect the bare scan, and
// expand the page into a zoomable full-screen lightbox to check the value.

import { useEffect, useState } from "react";
import { Eye, EyeOff, ImageOff, Maximize2, ScanSearch } from "lucide-react";
import { api } from "../../api/client";
import type { Field } from "../../api/types";
import { classNames } from "../../lib/ui";
import { HighlightBox } from "./HighlightBox";
import PageLightbox from "./PageLightbox";

const ZOOM_STEPS = [1, 1.5, 2, 3];

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
  const [showOverlay, setShowOverlay] = useState(true);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [zoom, setZoom] = useState(1);
  const src = api.pageImageUrl(field.document_id, field.page_no);
  const hasBox = !!field.bbox;
  const accent: "rose" | "brand" =
    field.flags.some((f) => f.severity === "error") ? "rose" : "brand";

  // Reset image probing whenever the page changes.
  useEffect(() => {
    setImgState("loading");
  }, [src]);

  // A different field may not have an image — never leave the lightbox open
  // pointing at the wrong/absent page.
  useEffect(() => {
    setLightboxOpen(false);
    setZoom(1);
  }, [field.id]);

  const showSchematic = imgState !== "ok";
  const canZoom = imgState === "ok"; // only the real image is worth enlarging

  function zoomIn() {
    setZoom((z) => ZOOM_STEPS.find((s) => s > z) ?? z);
  }
  function zoomOut() {
    setZoom((z) => [...ZOOM_STEPS].reverse().find((s) => s < z) ?? z);
  }
  function openLightbox() {
    if (!canZoom) return;
    setZoom(1);
    setLightboxOpen(true);
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400">
          <ScanSearch className="h-3.5 w-3.5" /> Page {field.page_no}
        </div>
        <div className="flex items-center gap-1.5">
          {showSchematic && imgState === "error" && (
            <span className="chip bg-slate-100 text-slate-500 ring-1 ring-inset ring-slate-200">
              <ImageOff className="h-3.5 w-3.5" /> schematic placeholder
            </span>
          )}
          {hasBox && (
            <button
              type="button"
              onClick={() => setShowOverlay((v) => !v)}
              aria-label={showOverlay ? "Hide highlight overlay" : "Show highlight overlay"}
              aria-pressed={showOverlay}
              title={showOverlay ? "Hide highlight" : "Show highlight"}
              className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40"
            >
              {showOverlay ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
            </button>
          )}
          {canZoom && (
            <button
              type="button"
              onClick={openLightbox}
              aria-label="Expand page to zoomable view"
              title="Expand & zoom"
              className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40"
            >
              <Maximize2 className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      <div className="relative mx-auto w-full max-w-[320px]">
        <div
          className={classNames(
            "group relative w-full overflow-hidden rounded-lg border border-slate-200 bg-white shadow-card",
            canZoom && "cursor-zoom-in",
          )}
          style={{ aspectRatio: "1 / 1.414" }}
          onClick={canZoom ? openLightbox : undefined}
          role={canZoom ? "button" : undefined}
          tabIndex={canZoom ? 0 : undefined}
          aria-label={canZoom ? "Expand page to zoomable view" : undefined}
          onKeyDown={
            canZoom
              ? (e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    openLightbox();
                  }
                }
              : undefined
          }
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
            showOverlay && <HighlightBox field={field} accent={accent} />
          ) : (
            <div className="absolute inset-0 grid place-items-center p-4">
              <div className="rounded-lg border border-dashed border-slate-300 bg-white/70 px-3 py-2 text-center text-xs text-slate-400">
                No location available for this field.
              </div>
            </div>
          )}

          {/* Hover affordance hinting the scan can be opened. */}
          {canZoom && (
            <span className="pointer-events-none absolute bottom-2 right-2 inline-flex items-center gap-1 rounded-md bg-slate-900/70 px-1.5 py-0.5 text-[10px] font-medium text-white opacity-0 transition-opacity group-hover:opacity-100">
              <Maximize2 className="h-3 w-3" /> Click to zoom
            </span>
          )}
        </div>

        <p className="mt-2 text-center text-[11px] text-slate-400">
          {showSchematic
            ? hasBox
              ? "Page image unavailable — schematic shows the field's position."
              : "Page image unavailable."
            : hasBox && !showOverlay
              ? "Highlight hidden — showing the raw scan."
              : "Highlighted region marks the extracted value."}
        </p>
      </div>

      {lightboxOpen && canZoom && (
        <PageLightbox
          field={field}
          src={src}
          accent={accent}
          hasBox={hasBox}
          showOverlay={showOverlay}
          onToggleOverlay={() => setShowOverlay((v) => !v)}
          zoom={zoom}
          onZoomIn={zoomIn}
          onZoomOut={zoomOut}
          onClose={() => setLightboxOpen(false)}
        />
      )}
    </div>
  );
}
