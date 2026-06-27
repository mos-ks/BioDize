// Design-system helpers: enum metadata (colors/labels/icons), formatters, and
// small data-fetching hooks. Frozen shared layer — pages import from here.

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Ban,
  Binary,
  CalendarClock,
  Calculator,
  CircleSlash,
  Clock,
  Equal,
  Eye,
  FileWarning,
  GitCompareArrows,
  Hash,
  Ruler,
  ScanLine,
  Sigma,
  type LucideIcon,
} from "lucide-react";
import type { FieldStatus, FlagCategory, Severity } from "../api/types";

// --- Severity ---------------------------------------------------------------

export interface ToneMeta {
  label: string;
  /** badge classes (bg + text + ring) */
  badge: string;
  /** solid dot / accent color class (text-*) */
  dot: string;
  /** subtle row tint */
  tint: string;
  /** left accent border */
  border: string;
  icon: LucideIcon;
}

export const SEVERITY_META: Record<Severity, ToneMeta> = {
  error: {
    label: "Error",
    badge: "bg-rose-50 text-rose-700 ring-1 ring-inset ring-rose-200",
    dot: "text-rose-500",
    tint: "bg-rose-50/60",
    border: "border-rose-400",
    icon: Ban,
  },
  warning: {
    label: "Warning",
    badge: "bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200",
    dot: "text-amber-500",
    tint: "bg-amber-50/60",
    border: "border-amber-400",
    icon: AlertTriangle,
  },
};

export function severityMeta(s: Severity | string): ToneMeta {
  return SEVERITY_META[s as Severity] ?? SEVERITY_META.warning;
}

// --- Field status -----------------------------------------------------------

export interface StatusMeta {
  label: string;
  badge: string;
  dot: string;
}

export const STATUS_META: Record<FieldStatus, StatusMeta> = {
  extracted: { label: "Extracted", badge: "bg-slate-100 text-slate-600 ring-1 ring-inset ring-slate-200", dot: "bg-slate-400" },
  validated: { label: "Validated", badge: "bg-slate-100 text-slate-600 ring-1 ring-inset ring-slate-200", dot: "bg-slate-400" },
  auto_accepted: { label: "Auto-accepted", badge: "bg-brand-50 text-brand-700 ring-1 ring-inset ring-brand-200", dot: "bg-brand-500" },
  needs_review: { label: "Needs review", badge: "bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200", dot: "bg-amber-500" },
  confirmed: { label: "Confirmed", badge: "bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-200", dot: "bg-emerald-500" },
  corrected: { label: "Corrected", badge: "bg-sky-50 text-sky-700 ring-1 ring-inset ring-sky-200", dot: "bg-sky-500" },
};

export function statusMeta(s: FieldStatus | string): StatusMeta {
  return STATUS_META[s as FieldStatus] ?? STATUS_META.extracted;
}

export const RESOLVED_STATUSES: FieldStatus[] = ["confirmed", "corrected", "auto_accepted"];

// --- Flag category ----------------------------------------------------------

export interface CategoryMeta {
  label: string;
  icon: LucideIcon;
  /** accent text color */
  color: string;
}

export const CATEGORY_META: Record<FlagCategory, CategoryMeta> = {
  extraction: { label: "Extraction", icon: ScanLine, color: "text-violet-600" },
  calculation: { label: "Calculation", icon: Calculator, color: "text-indigo-600" },
  range: { label: "Range", icon: Ruler, color: "text-orange-600" },
  temporal: { label: "Temporal", icon: CalendarClock, color: "text-cyan-600" },
  four_eyes: { label: "Four-eyes", icon: Eye, color: "text-fuchsia-600" },
  format: { label: "Format", icon: Hash, color: "text-teal-600" },
  applicability: { label: "Applicability", icon: CircleSlash, color: "text-slate-600" },
  cross_reference: { label: "Cross-reference", icon: GitCompareArrows, color: "text-blue-600" },
  deviation: { label: "Deviation", icon: FileWarning, color: "text-amber-600" },
  outlier: { label: "Outlier", icon: Sigma, color: "text-pink-600" },
  missing: { label: "Missing", icon: Ban, color: "text-rose-600" },
};

export function categoryMeta(c: FlagCategory | string): CategoryMeta {
  return CATEGORY_META[c as FlagCategory] ?? { label: c, icon: FileWarning, color: "text-slate-600" };
}

// --- Roles (semantic field roles -> human labels + icons) -------------------

export const ROLE_LABELS: Record<string, string> = {
  tare_mass: "Tare mass",
  gross_mass: "Gross mass",
  net_mass: "Net mass",
  volume: "Volume",
  density: "Density (ρ)",
  concentration: "Concentration (c)",
  hold_start: "Hold start",
  hold_end: "Hold end",
  hold_duration: "Hold duration",
  temperature_setpoint: "Temperature setpoint",
  calc_input: "Calc input",
  calc_result: "Calc result",
  signature_processed: "Bearbeitet (processed)",
  signature_checked: "Geprüft (checked)",
  gate: "Gate",
  checkbox_single: "Single-select",
  checkbox_bool: "Checkbox",
  sample_id: "Sample ID",
  equipment_id: "Equipment ID",
  deviation_ref: "Deviation ref",
  text: "Text",
};

export function roleLabel(role?: string | null): string {
  if (!role) return "—";
  return ROLE_LABELS[role] ?? humanize(role);
}

export function roleIcon(role?: string | null): LucideIcon {
  if (!role) return Binary;
  if (role.includes("mass")) return Equal;
  if (role === "volume" || role === "density" || role === "concentration") return Sigma;
  if (role.startsWith("hold") || role.includes("temperature")) return Clock;
  if (role.startsWith("calc")) return Calculator;
  if (role.startsWith("signature")) return Eye;
  if (role.includes("checkbox") || role === "gate") return CircleSlash;
  return Binary;
}

// --- Formatters -------------------------------------------------------------

export function humanize(s: string): string {
  return s
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());
}

export function confidencePct(conf: number): number {
  return Math.round(Math.max(0, Math.min(1, conf)) * 100);
}

/** Bucketed confidence tone for meters/labels. */
export function confidenceTone(conf: number): { label: string; bar: string; text: string } {
  if (conf >= 0.9) return { label: "High", bar: "bg-brand-500", text: "text-brand-700" };
  if (conf >= 0.75) return { label: "Medium", bar: "bg-amber-400", text: "text-amber-700" };
  return { label: "Low", bar: "bg-rose-400", text: "text-rose-700" };
}

export function fieldDisplayValue(value?: string | null, raw?: string | null): string {
  const v = value ?? raw;
  return v && v.trim() ? v : "—";
}

/** Worst severity among flags (error beats warning). null when clean. */
export function worstSeverity(flags: { severity: Severity }[]): Severity | null {
  if (flags.some((f) => f.severity === "error")) return "error";
  if (flags.some((f) => f.severity === "warning")) return "warning";
  return null;
}

/** The most relevant flag to surface for a field: first error, else first flag. */
export function primaryFlag<T extends { severity: Severity }>(flags: T[]): T | null {
  return flags.find((f) => f.severity === "error") ?? flags[0] ?? null;
}

// --- Hooks ------------------------------------------------------------------

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

/**
 * Fetch-on-mount hook. `deps` controls refetch; `reload()` forces it.
 * Guards against setting state after unmount / stale responses.
 */
export function useApi<T>(fn: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    fnRef
      .current()
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((e) => {
        if (alive) setError(e?.message ?? String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, loading, error, reload };
}

/** Run an async action with pending/error tracking (for mutations). */
export function useAsyncAction<Args extends unknown[], R>(
  fn: (...args: Args) => Promise<R>,
): { run: (...args: Args) => Promise<R | undefined>; pending: boolean; error: string | null } {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(
    async (...args: Args) => {
      setPending(true);
      setError(null);
      try {
        return await fn(...args);
      } catch (e: any) {
        setError(e?.message ?? String(e));
        return undefined;
      } finally {
        setPending(false);
      }
    },
    [fn],
  );
  return { run, pending, error };
}

export function classNames(...xs: (string | false | null | undefined)[]): string {
  return xs.filter(Boolean).join(" ");
}
