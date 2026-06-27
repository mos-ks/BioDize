// Top document bar for the review workspace: identity, status, tallies, and
// navigation/export actions. Read-only — data is owned by ReviewPage.

import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, BarChart3, FileSpreadsheet, Gauge } from "lucide-react";
import { api } from "../../api/client";
import type { DocumentSummary } from "../../api/types";
import { CountPill, StatusBadge } from "../../components/atoms";
import EvalModal from "./EvalModal";

export default function DocumentBar({ doc }: { doc: DocumentSummary }) {
  const [evalOpen, setEvalOpen] = useState(false);
  return (
    <div className="card animate-fade-in flex flex-col gap-3 px-4 py-3 sm:px-5 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex min-w-0 items-start gap-3">
        <Link
          to="/"
          className="btn-ghost mt-0.5 shrink-0 px-2 py-1.5"
          title="Back to documents"
          aria-label="Back to documents"
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm font-semibold text-slate-800">{doc.doc_no}</span>
            <StatusBadge status={doc.status === "processed" ? "validated" : "extracted"} />
            <span className="chip bg-slate-100 text-slate-500 ring-1 ring-inset ring-slate-200">
              {doc.page_count} pages
            </span>
          </div>
          {doc.title && (
            <h1 className="mt-0.5 truncate text-[15px] font-semibold text-slate-700" title={doc.title}>
              {doc.title}
            </h1>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1.5">
          <CountPill tone="error" count={doc.n_errors} label="errors" />
          <CountPill tone="warning" count={doc.n_warnings} label="warnings" />
          <CountPill tone="neutral" count={doc.n_needs_review} label="to review" />
        </div>
        <div className="mx-1 hidden h-6 w-px bg-slate-200 lg:block" />
        <button type="button" onClick={() => setEvalOpen(true)} className="btn-secondary">
          <Gauge className="h-4 w-4" /> Eval AI
        </button>
        <Link to={`/documents/${doc.id}/stats`} className="btn-secondary">
          <BarChart3 className="h-4 w-4" /> Stats
        </Link>
        <a href={api.exportUrl(doc.id)} download className="btn-accent">
          <FileSpreadsheet className="h-4 w-4" /> Export .xlsx
        </a>
      </div>

      {evalOpen && <EvalModal documentId={doc.id} onClose={() => setEvalOpen(false)} />}
    </div>
  );
}
