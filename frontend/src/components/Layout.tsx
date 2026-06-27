// App shell: top bar with brand, live backend/health indicator, and a runtime
// API-base settings dialog (so the static build retargets without a rebuild).

import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Activity, Check, RotateCcw, Server, Settings2, X } from "lucide-react";
import { api, defaultApiBase, getApiBase, resetApiBase, setApiBase } from "../api/client";
import type { Health } from "../api/types";
import { classNames } from "../lib/ui";
import { Spinner } from "./atoms";

function Brand() {
  return (
    <Link to="/" className="flex items-center gap-2.5">
      <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-sm">
        <svg
          viewBox="0 0 32 32"
          className="h-[22px] w-[22px]"
          fill="none"
          stroke="currentColor"
          strokeWidth={2.3}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
        >
          {/* pharma capsule — one half tinted */}
          <g transform="rotate(-32 13 13)">
            <rect x="5" y="9.5" width="16" height="7" rx="3.5" />
            <path d="M13 9.5 V16.5 M21 13 a3.5 3.5 0 0 0 -3.5 -3.5 H13 v7 h4.5 A3.5 3.5 0 0 0 21 13 Z"
                  fill="currentColor" fillOpacity={0.35} stroke="none" />
          </g>
          {/* rising analytics line */}
          <polyline points="16 25 20 20 23.5 22.5 28 15.5" />
        </svg>
      </span>
      <div className="leading-tight">
        <div className="text-[15px] font-bold tracking-tight text-slate-800">
          Bio<span className="text-brand-600">Dize</span>
        </div>
        <div className="text-[11px] font-medium text-slate-400">Batch Record Review</div>
      </div>
    </Link>
  );
}

function HealthDot({ health, loading, error }: { health: Health | null; loading: boolean; error: boolean }) {
  const color = error ? "bg-rose-500" : loading ? "bg-slate-300" : "bg-brand-500";
  const ping = !error && !loading;
  return (
    <span className="relative flex h-2.5 w-2.5">
      {ping && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-400 opacity-60" />}
      <span className={classNames("relative inline-flex h-2.5 w-2.5 rounded-full", color)} />
    </span>
  );
}

function ApiSettings({ onClose }: { onClose: () => void }) {
  const [value, setValue] = useState(getApiBase());
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);

  async function test(base?: string) {
    const target = (base ?? value).replace(/\/+$/, "");
    setTesting(true);
    setResult(null);
    try {
      const res = await fetch(`${target}/health`, { headers: { Accept: "application/json" } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const h = (await res.json()) as Health;
      setResult({ ok: true, msg: `Connected · extractor=${h.extractor} · ocr=${h.ocr_engine} · db=${h.db}` });
    } catch (e: any) {
      setResult({ ok: false, msg: e?.message ?? "Unreachable" });
    } finally {
      setTesting(false);
    }
  }

  function save() {
    setApiBase(value);
    window.location.reload();
  }
  function reset() {
    resetApiBase();
    setValue(defaultApiBase());
    window.location.reload();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/30 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className="mt-24 w-full max-w-lg animate-slide-up rounded-2xl border border-slate-200 bg-white p-5 shadow-panel"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-800">
            <Server className="h-4 w-4 text-brand-600" /> Backend API
          </h2>
          <button onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600">
            <X className="h-4 w-4" />
          </button>
        </div>
        <p className="mt-1 text-sm text-slate-500">
          Point the app at any BioDize backend. Saved to this browser — no rebuild needed.
        </p>

        <label className="mt-4 block text-xs font-semibold uppercase tracking-wide text-slate-400">Base URL</label>
        <input
          className="input mt-1 font-mono text-[13px]"
          value={value}
          spellCheck={false}
          autoFocus
          onChange={(e) => setValue(e.target.value)}
          placeholder="https://api.biodize.tech"
          onKeyDown={(e) => e.key === "Enter" && test()}
        />

        {result && (
          <div
            className={classNames(
              "mt-3 flex items-start gap-2 rounded-lg px-3 py-2 text-sm",
              result.ok ? "bg-brand-50 text-brand-700" : "bg-rose-50 text-rose-700",
            )}
          >
            {result.ok ? <Check className="mt-0.5 h-4 w-4 shrink-0" /> : <X className="mt-0.5 h-4 w-4 shrink-0" />}
            <span className="break-words">{result.msg}</span>
          </div>
        )}

        <div className="mt-5 flex items-center justify-between">
          <button onClick={reset} className="btn-ghost text-xs">
            <RotateCcw className="h-3.5 w-3.5" /> Reset to default
          </button>
          <div className="flex gap-2">
            <button onClick={() => test()} className="btn-secondary" disabled={testing}>
              {testing ? <Spinner /> : <Activity className="h-4 w-4" />} Test
            </button>
            <button onClick={save} className="btn-primary">
              <Check className="h-4 w-4" /> Save &amp; reload
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const loc = useLocation();

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(false);
    api
      .health()
      .then((h) => alive && setHealth(h))
      .catch(() => alive && setError(true))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [loc.key === "default"]); // refetch once on first mount

  const base = getApiBase();
  const shortBase = base.replace(/^https?:\/\//, "");

  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/85 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1500px] items-center justify-between gap-4 px-4 sm:px-6">
          <Brand />
          <button
            onClick={() => setOpen(true)}
            className="group flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-2.5 py-2 transition hover:border-slate-300 hover:shadow-sm"
            title={
              loading
                ? "Checking backend…"
                : error
                  ? "Backend unreachable — click to configure"
                  : health
                    ? `Connected · ${shortBase} · ${health.extractor} · ${health.ocr_engine}`
                    : "Backend settings"
            }
            aria-label="Backend settings"
          >
            <HealthDot health={health} loading={loading} error={error} />
            <Settings2 className="h-4 w-4 text-slate-400 group-hover:text-slate-600" />
          </button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1500px] flex-1 px-4 py-6 sm:px-6">{children}</main>

      <footer className="border-t border-slate-200/70 py-4">
        <div className="mx-auto flex max-w-[1500px] flex-col items-center justify-between gap-1 px-6 text-xs text-slate-400 sm:flex-row">
          <span>BioDize · digitize · validate · review handwritten batch records</span>
          <span>Right or it asks — never silently wrong.</span>
        </div>
      </footer>

      {open && <ApiSettings onClose={() => setOpen(false)} />}
    </div>
  );
}
