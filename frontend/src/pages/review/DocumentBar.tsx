// Top document bar for the review workspace: identity, status, tallies, and
// navigation/export actions. Read-only — data is owned by ReviewPage.

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, BarChart3, ChevronDown, Download, FileSpreadsheet, FileText, History, Trash2 } from "lucide-react";
import { api } from "../../api/client";
import type { DocumentSummary } from "../../api/types";
import { CountPill, SimulatedBadge, StatusBadge } from "../../components/atoms";
import { classNames, displayDocNo, isSimulatedDoc, prettyDocTitle } from "../../lib/ui";

export default function DocumentBar({ doc }: { doc: DocumentSummary }) {
  const [deleting, setDeleting] = useState(false);
  const [dlOpen, setDlOpen] = useState(false);
  const navigate = useNavigate();

  async function onDelete() {
    if (!window.confirm(`Delete "${prettyDocTitle(doc.title)}"? This permanently removes the batch record and all its data.`))
      return;
    setDeleting(true);
    try {
      await api.deleteDocument(doc.id);
      navigate("/");
    } catch {
      setDeleting(false);
    }
  }

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
            <span className="font-mono text-sm font-semibold text-slate-800">{displayDocNo(doc.doc_no)}</span>
            <StatusBadge status={doc.status === "processed" ? "validated" : "extracted"} />
            {isSimulatedDoc(doc) && <SimulatedBadge />}
            <span className="chip bg-slate-100 text-slate-500 ring-1 ring-inset ring-slate-200">
              {doc.page_count} pages
            </span>
          </div>
          <h1 className="mt-0.5 truncate text-[15px] font-semibold text-slate-700" title={prettyDocTitle(doc.title)}>
            {prettyDocTitle(doc.title)}
          </h1>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1.5">
          <CountPill tone="error" count={doc.n_errors} label="errors" />
          <CountPill tone="warning" count={doc.n_warnings} label="warnings" />
          <CountPill tone="neutral" count={doc.n_needs_review} label="to review" />
        </div>
        <div className="mx-1 hidden h-6 w-px bg-slate-200 lg:block" />
        <Link to={`/documents/${doc.id}/stats`} className="btn-secondary">
          <BarChart3 className="h-4 w-4" /> Stats
        </Link>
        <div className="relative">
          <button type="button" onClick={() => setDlOpen((v) => !v)} className="btn-accent" aria-expanded={dlOpen}>
            <Download className="h-4 w-4" /> Download <ChevronDown className="h-3.5 w-3.5" />
          </button>
          {dlOpen && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setDlOpen(false)} />
              <div className="absolute right-0 z-20 mt-1 w-56 rounded-xl border border-slate-200 bg-white p-1 shadow-panel">
                {[
                  { href: api.exportUrl(doc.id), icon: FileSpreadsheet, color: "text-emerald-600", label: "Excel — Solution (.xlsx)" },
                  { href: api.csvUrl(doc.id), icon: FileText, color: "text-slate-500", label: "Full data (.csv)" },
                  { href: api.changelogUrl(doc.id), icon: History, color: "text-violet-600", label: "Change log (.csv)" },
                ].map((it) => (
                  <a
                    key={it.label}
                    href={it.href}
                    download
                    onClick={() => setDlOpen(false)}
                    className={classNames("flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-slate-700 hover:bg-slate-100")}
                  >
                    <it.icon className={classNames("h-4 w-4", it.color)} /> {it.label}
                  </a>
                ))}
              </div>
            </>
          )}
        </div>
        <button
          type="button"
          onClick={onDelete}
          disabled={deleting}
          title="Delete this batch record"
          aria-label="Delete this batch record"
          className="btn-ghost px-2 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
