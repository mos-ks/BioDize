// Scroll the whole document: every page scan stacked vertically with all of its
// detection boxes overlaid (error=red, warning=amber, clean=blue). Click any box
// to open that field's review detail. Shown in the right pane when nothing is
// selected, so opening a batch lets you scroll the PDF straight away.

import { useRef, useState } from "react";
import { Eye, EyeOff, ImageOff, MapPinPlus } from "lucide-react";
import { api } from "../../api/client";
import type { Field } from "../../api/types";
import { classNames, useApi } from "../../lib/ui";
import { AllBoxesOverlay } from "./AllBoxesOverlay";
import { LoadingBlock } from "../../components/atoms";
import AnnotationForm from "./AnnotationForm";

function PageItem({
  documentId,
  pageNo,
  fields,
  onSelect,
  showBoxes,
  annotate,
  onDraw,
}: {
  documentId: string;
  pageNo: number;
  fields: Field[];
  onSelect: (id: string) => void;
  showBoxes: boolean;
  annotate: boolean;
  onDraw: (pageNo: number, bbox: number[]) => void;
}) {
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");
  const [ratio, setRatio] = useState<number | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const src = api.pageImageUrl(documentId, pageNo);
  const nFlagged = fields.filter((f) => f.flags.length > 0).length;
  const nErr = fields.filter((f) => f.flags.some((fl) => fl.severity === "error")).length;

  // Annotate mode: a single click drops a flag at that spot. Build a small box
  // centered on the click so a pin renders exactly there.
  function clickPage(e: React.MouseEvent) {
    if (!annotate || state !== "ok") return;
    const r = wrapRef.current!.getBoundingClientRect();
    const c = (v: number) => Math.min(1, Math.max(0, v));
    const x = c((e.clientX - r.left) / r.width);
    const y = c((e.clientY - r.top) / r.height);
    const h = 0.012;
    const bb = [x - h, y - h, x + h, y + h].map((v) => +c(v).toFixed(4));
    onDraw(pageNo, bb);
  }

  return (
    <div className="scroll-mt-2">
      <div className="mb-1 flex items-center justify-between px-1 text-xs">
        <span className="font-semibold text-slate-600">Page {pageNo}</span>
        <span className="text-slate-400">
          {fields.length} field{fields.length !== 1 ? "s" : ""}
          {nErr > 0 && <span className="ml-1 font-semibold text-rose-500">· {nErr} error{nErr !== 1 ? "s" : ""}</span>}
          {nErr === 0 && nFlagged > 0 && (
            <span className="ml-1 font-semibold text-amber-500">· {nFlagged} flagged</span>
          )}
        </span>
      </div>
      <div
        ref={wrapRef}
        onClick={clickPage}
        className={classNames(
          "relative mx-auto w-full max-w-[640px] overflow-hidden rounded-lg border border-slate-200 bg-white shadow-card",
          annotate && state === "ok" && "cursor-crosshair ring-2 ring-violet-300",
        )}
        style={{ aspectRatio: ratio ? String(ratio) : "1 / 1.414" }}
      >
        {state !== "error" ? (
          // eslint-disable-next-line jsx-a11y/img-redundant-alt
          <img
            src={src}
            alt={`Scanned page ${pageNo}`}
            loading="lazy"
            draggable={false}
            className={classNames(
              "absolute inset-0 h-full w-full object-contain",
              state === "ok" ? "opacity-100" : "opacity-0",
            )}
            onLoad={(e) => {
              setState("ok");
              const t = e.currentTarget;
              if (t.naturalWidth && t.naturalHeight) setRatio(t.naturalWidth / t.naturalHeight);
            }}
            onError={() => setState("error")}
          />
        ) : (
          <div className="absolute inset-0 grid place-items-center gap-1 text-slate-300">
            <ImageOff className="h-7 w-7" />
            <span className="text-[11px] text-slate-400">No scan for this page</span>
          </div>
        )}
        {state === "ok" && showBoxes && (
          <AllBoxesOverlay fields={fields} currentFieldId="" onSelect={annotate ? undefined : onSelect} />
        )}
      </div>
    </div>
  );
}

export default function PdfScroll({
  documentId,
  pageCount,
  onSelect,
  onAnnotated,
}: {
  documentId: string;
  pageCount: number;
  onSelect: (id: string) => void;
  onAnnotated?: () => void;
}) {
  const { data: fields, loading, reload } = useApi<Field[]>(() => api.listFields(documentId, {}), [documentId]);
  const [showBoxes, setShowBoxes] = useState(true);
  const [annotate, setAnnotate] = useState(false);
  const [draft, setDraft] = useState<{ pageNo: number; bbox: number[] } | null>(null);

  const byPage = new Map<number, Field[]>();
  for (const f of fields ?? []) {
    const arr = byPage.get(f.page_no);
    if (arr) arr.push(f);
    else byPage.set(f.page_no, [f]);
  }
  // Cover declared page_count, but also any page a field lives on (just in case).
  const lastPage = Math.max(pageCount, ...(byPage.size ? [...byPage.keys()] : [0]));
  const pages = Array.from({ length: Math.max(lastPage, 0) }, (_, i) => i + 1);

  if (loading) return <LoadingBlock label="Loading the document…" />;

  return (
    <div className="animate-fade-in space-y-2">
      <div className="sticky top-0 z-10 -mx-1 flex items-center justify-between gap-2 bg-white/90 px-1 pb-2 backdrop-blur">
        <h2 className="text-base font-semibold text-slate-800">Document</h2>
        <div className="flex items-center gap-2">
          <span className="hidden text-xs text-slate-400 sm:inline">
            {annotate ? "click a spot to flag it" : "click a pin to review"}
          </span>
          <button
            type="button"
            onClick={() => setAnnotate((v) => !v)}
            aria-pressed={annotate}
            title={annotate ? "Stop flagging" : "Click a spot on the PDF to add a human flag"}
            className={classNames(
              "inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium transition-colors",
              annotate
                ? "bg-violet-600 text-white ring-1 ring-inset ring-violet-600 hover:bg-violet-700"
                : "text-slate-500 ring-1 ring-inset ring-slate-200 hover:bg-slate-100",
            )}
          >
            <MapPinPlus className="h-3.5 w-3.5" /> {annotate ? "Click to flag…" : "Add flag"}
          </button>
          <button
            type="button"
            onClick={() => setShowBoxes((v) => !v)}
            aria-pressed={showBoxes}
            title={showBoxes ? "Hide all detections" : "Show all detections"}
            className={classNames(
              "inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium transition-colors",
              showBoxes
                ? "bg-brand-50 text-brand-700 ring-1 ring-inset ring-brand-200 hover:bg-brand-100"
                : "text-slate-500 ring-1 ring-inset ring-slate-200 hover:bg-slate-100",
            )}
          >
            {showBoxes ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
            Detections
          </button>
        </div>
      </div>
      <div className="space-y-5">
        {pages.map((pg) => (
          <PageItem
            key={pg}
            documentId={documentId}
            pageNo={pg}
            fields={byPage.get(pg) ?? []}
            onSelect={onSelect}
            showBoxes={showBoxes}
            annotate={annotate}
            onDraw={(pageNo, bbox) => setDraft({ pageNo, bbox })}
          />
        ))}
      </div>

      {draft && (
        <AnnotationForm
          documentId={documentId}
          pageNo={draft.pageNo}
          bbox={draft.bbox}
          onClose={() => setDraft(null)}
          onSaved={() => {
            reload();
            onAnnotated?.();
          }}
        />
      )}
    </div>
  );
}
