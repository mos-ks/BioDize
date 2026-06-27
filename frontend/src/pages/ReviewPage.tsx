// ReviewPage — the centerpiece review experience for a single batch record.
//
// Layout: a top document bar, then a tall two-column workspace. Left = a tabbed
// list pane (Queue / All fields / Flags); right = the detail + confirm/correct
// flow. Both panes scroll independently and the whole thing fits the viewport.
//
// Review flow: the queue is ordered errors -> warnings -> low-confidence by the
// backend. Selecting a row opens its detail; confirming/correcting it patches
// the field, refreshes the queue + document tallies, and auto-advances to the
// next item for a fast keyboard-light review loop.

import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ListChecks, PartyPopper, ScanLine, Sparkles, Table2 } from "lucide-react";
import { api } from "../api/client";
import type { DocumentSummary, Field } from "../api/types";
import { classNames, useApi } from "../lib/ui";
import { ErrorBlock, LoadingBlock } from "../components/atoms";
import DocumentBar from "./review/DocumentBar";
import FieldDetail from "./review/FieldDetail";
import ExtractionList from "./review/ExtractionList";
import PageGroupedQueue from "./review/PageGroupedQueue";
import PdfScroll from "./review/PdfScroll";

type Tab = "queue" | "extraction";

export default function ReviewPage() {
  const { documentId = "" } = useParams();
  const navigate = useNavigate();

  const [tab, setTab] = useState<Tab>("queue");
  // No field is selected by default when a batch opens — the reviewer picks one.
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const docState = useApi<DocumentSummary>(() => api.getDocument(documentId), [documentId]);
  const queueState = useApi<Field[]>(() => api.getQueue(documentId), [documentId]);

  const queue = useMemo(() => queueState.data ?? [], [queueState.data]);

  function selectField(id: string) {
    setSelectedId(id);
  }

  // After a confirm/correct: refresh tallies + queue, then advance to the next
  // unresolved queue item (or clear selection when the queue empties).
  function handleResolved() {
    const idx = queue.findIndex((f) => f.id === selectedId);
    const next = idx >= 0 ? queue.slice(idx + 1).find((f) => f.id !== selectedId) : undefined;
    setSelectedId(next ? next.id : null);
    docState.reload();
    queueState.reload();
  }

  function advanceToNext() {
    const idx = queue.findIndex((f) => f.id === selectedId);
    const next = idx >= 0 ? queue[idx + 1] : queue[0];
    setSelectedId(next ? next.id : null);
  }

  const selectedIndex = selectedId ? queue.findIndex((f) => f.id === selectedId) : -1;
  const hasNext = selectedIndex >= 0 && selectedIndex < queue.length - 1;

  // The Queue badge counts distinct PAGES needing review, not error-fields.
  const pagesNeedingReview = useMemo(
    () => new Set(queue.map((f) => f.page_no)).size,
    [queue],
  );

  const tabs: { id: Tab; label: string; icon: typeof ListChecks; count?: number; title?: string }[] = [
    {
      id: "queue",
      label: "Queue",
      icon: ListChecks,
      count: pagesNeedingReview,
      title: "Pages needing review",
    },
    { id: "extraction", label: "Extraction", icon: ScanLine },
  ];

  // --- Document-level load/error gate ---------------------------------------
  if (docState.loading) return <LoadingBlock label="Loading document…" />;
  if (docState.error || !docState.data)
    return (
      <ErrorBlock
        message={docState.error ?? "Document not found."}
        onRetry={() => {
          docState.reload();
          queueState.reload();
        }}
      />
    );

  return (
    <div className="flex flex-col gap-4">
      <DocumentBar doc={docState.data} />

      <div className="grid min-h-0 grid-cols-1 gap-4 lg:grid-cols-[minmax(360px,440px)_minmax(0,1fr)] lg:h-[calc(100vh-12rem)]">
        {/* LEFT PANE — tabbed list */}
        <section className="flex min-h-0 flex-col">
          <div className="flex shrink-0 items-center gap-1 rounded-xl border border-slate-200 bg-white p-1 shadow-card">
            {tabs.map((t) => {
              const Icon = t.icon;
              const selected = tab === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  title={t.title}
                  className={classNames(
                    "flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2 py-2 text-sm font-medium transition-colors",
                    selected ? "bg-brand-600 text-white shadow-sm" : "text-slate-500 hover:bg-slate-100",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  <span className="hidden sm:inline">{t.label}</span>
                  {t.count !== undefined && t.count > 0 && (
                    <span
                      title={t.title}
                      className={classNames(
                        "rounded-full px-1.5 text-xs font-semibold tabular-nums",
                        selected ? "bg-white/20 text-white" : "bg-slate-200 text-slate-600",
                      )}
                    >
                      {t.count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          <div className="mt-3 min-h-0 flex-1 overflow-y-auto pr-1">
            {tab === "queue" && (
              <PageGroupedQueue documentId={documentId} selectedId={selectedId} onSelect={selectField} />
            )}
            {tab === "extraction" && (
              <ExtractionList documentId={documentId} activeId={selectedId} onSelect={selectField} />
            )}
          </div>
        </section>

        {/* RIGHT PANE — detail */}
        <section className="min-h-0 lg:overflow-y-auto">
          <div className="card min-h-full p-4 sm:p-5">
            {selectedId ? (
              <FieldDetail
                key={selectedId}
                fieldId={selectedId}
                onResolved={handleResolved}
                hasNext={hasNext}
                onSkipNext={advanceToNext}
              />
            ) : queue.length === 0 ? (
              <AllClear onBrowseAll={() => setTab("extraction")} onStats={() => navigate(`/documents/${documentId}/stats`)} />
            ) : (
              // Nothing selected yet: scroll through the whole PDF with every detection
              // box overlaid; click a box to open its detail.
              <PdfScroll
                documentId={documentId}
                pageCount={docState.data.page_count}
                onSelect={selectField}
                onAnnotated={() => {
                  docState.reload();
                  queueState.reload();
                }}
              />
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function AllClear({ onBrowseAll, onStats }: { onBrowseAll: () => void; onStats: () => void }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 rounded-xl bg-gradient-to-b from-brand-50/70 to-white px-6 py-16 text-center animate-slide-up">
      <div className="grid h-16 w-16 place-items-center rounded-2xl bg-brand-100 text-brand-600 shadow-sm">
        <PartyPopper className="h-8 w-8" />
      </div>
      <div>
        <h2 className="text-xl font-bold text-slate-800">All clear</h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
          Every field on this record is auto-accepted or human-confirmed. Right or it asks — and right
          now, nothing is asking.
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-2">
        <button onClick={onBrowseAll} className="btn-secondary">
          <Table2 className="h-4 w-4" /> Browse extraction
        </button>
        <button onClick={onStats} className="btn-primary">
          <Sparkles className="h-4 w-4" /> View stats
        </button>
      </div>
    </div>
  );
}
