// StatsPage — analytics for one document: a validation-flag dashboard and
// hand-rolled value distributions per numeric role.

import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  BarChart3,
  Home,
  Info,
  LineChart,
  ListChecks,
} from "lucide-react";
import { api } from "../api/client";
import type { Field } from "../api/types";
import {
  classNames,
  roleIcon,
  roleLabel,
  useApi,
} from "../lib/ui";
import {
  Card,
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  SectionLabel,
  Stat,
} from "../components/atoms";
import { FlagsDashboard } from "./stats/FlagsDashboard";
import { Histogram, fmtNum } from "./stats/Histogram";

// Numeric roles that have meaningful value distributions (per the brief).
const NUMERIC_ROLES = [
  "tare_mass",
  "gross_mass",
  "net_mass",
  "volume",
  "density",
  "concentration",
  "calc_input",
  "calc_result",
  "hold_duration",
] as const;

const NUMERIC_ROLE_SET = new Set<string>(NUMERIC_ROLES);

/** A unit seen for a role in this document, if any field carries one. */
function unitForRole(fields: Field[], role: string): string | null {
  const f = fields.find((x) => x.role === role && x.unit && x.unit.trim());
  return f?.unit ?? null;
}

function DistributionPanel({
  role,
  unit,
}: {
  role: string;
  unit: string | null;
}) {
  const dist = useApi(() => api.getDistribution(role), [role]);

  if (dist.loading) return <LoadingBlock label={`Loading ${roleLabel(role)} distribution…`} />;
  if (dist.error) return <ErrorBlock message={dist.error} onRetry={dist.reload} />;
  if (!dist.data) return null;

  const d = dist.data;

  if (d.n === 0) {
    return (
      <EmptyState
        icon={<LineChart className="h-8 w-8" />}
        title="No history yet for this role"
        hint="Distributions aggregate only confirmed, corrected, or auto-accepted values. Confirm or correct this role's values in Review to start building its history."
        action={
          <span className="mt-1 inline-flex items-center gap-1.5 text-xs text-slate-400">
            <Info className="h-3.5 w-3.5" />
            aggregated across all documents
          </span>
        }
      />
    );
  }

  return (
    <div className="flex flex-col gap-5 animate-fade-in">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <Stat label="n" value={d.n} tone="good" hint="data points" />
        <Stat
          label="mean"
          value={d.mean != null ? fmtNum(d.mean) : "—"}
          hint={unit ?? undefined}
        />
        <Stat label="std" value={d.std != null ? fmtNum(d.std) : "—"} hint={unit ?? undefined} />
        <Stat label="min" value={d.min != null ? fmtNum(d.min) : "—"} hint={unit ?? undefined} />
        <Stat label="max" value={d.max != null ? fmtNum(d.max) : "—"} hint={unit ?? undefined} />
      </div>

      <Card className="p-4">
        <SectionLabel>Distribution</SectionLabel>
        <div className="mt-3">
          {d.histogram.length > 0 ? (
            <Histogram bins={d.histogram} unit={unit} min={d.min} max={d.max} />
          ) : (
            <p className="py-8 text-center text-sm text-slate-400">
              No histogram bins returned for this role.
            </p>
          )}
        </div>
      </Card>
    </div>
  );
}

function DistributionsSection({
  fields,
  documentId,
}: {
  fields: Field[];
  documentId: string;
}) {
  // Numeric roles actually present in this document, in canonical order.
  const presentRoles = useMemo<string[]>(() => {
    const seen = new Set<string>();
    for (const f of fields) {
      if (f.role && NUMERIC_ROLE_SET.has(f.role)) seen.add(f.role);
    }
    return NUMERIC_ROLES.filter((r) => seen.has(r));
  }, [fields]);

  const countByRole = useMemo(() => {
    const m = new Map<string, number>();
    for (const f of fields) {
      if (f.role && NUMERIC_ROLE_SET.has(f.role)) {
        m.set(f.role, (m.get(f.role) ?? 0) + 1);
      }
    }
    return m;
  }, [fields]);

  const [selected, setSelected] = useState<string | null>(null);
  // Roles with history (distribution n > 0), discovered by probing the stats
  // endpoint once. Used only to pick a sensible default selection.
  const [rolesWithHistory, setRolesWithHistory] = useState<Set<string> | null>(null);

  // Probe each present role's distribution once to find which have data.
  useEffect(() => {
    if (presentRoles.length === 0) {
      setRolesWithHistory(new Set());
      return;
    }
    let alive = true;
    setRolesWithHistory(null);
    Promise.all(
      presentRoles.map((role) =>
        api
          .getDistribution(role)
          .then((d) => (d.n > 0 ? role : null))
          .catch(() => null),
      ),
    ).then((results) => {
      if (!alive) return;
      setRolesWithHistory(new Set(results.filter((r): r is string => r != null)));
    });
    return () => {
      alive = false;
    };
  }, [presentRoles]);

  // Default-select: first role with history if any, else first present role.
  useEffect(() => {
    if (selected != null || rolesWithHistory == null) return;
    const firstWithHistory = presentRoles.find((r) => rolesWithHistory.has(r));
    setSelected(firstWithHistory ?? presentRoles[0] ?? null);
  }, [rolesWithHistory, presentRoles, selected]);

  if (presentRoles.length === 0) {
    return (
      <EmptyState
        icon={<BarChart3 className="h-8 w-8" />}
        title="No numeric roles in this document"
        hint="This document has no mass, volume, density, concentration, calculation, or duration fields to chart."
      />
    );
  }

  const activeRole = selected && presentRoles.includes(selected) ? selected : presentRoles[0];
  const unit = unitForRole(fields, activeRole);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        {presentRoles.map((role) => {
          const Icon = roleIcon(role);
          const active = role === activeRole;
          const count = countByRole.get(role) ?? 0;
          const hasHistory = rolesWithHistory?.has(role) ?? false;
          return (
            <button
              key={role}
              type="button"
              onClick={() => setSelected(role)}
              aria-pressed={active}
              className={classNames(
                "inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors",
                active
                  ? "border-brand-500 bg-brand-50 text-brand-700"
                  : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50",
              )}
            >
              <Icon className={classNames("h-4 w-4", active ? "text-brand-600" : "text-slate-400")} />
              {roleLabel(role)}
              {hasHistory && (
                <span
                  className="h-1.5 w-1.5 rounded-full bg-brand-500"
                  title="Has confirmed history"
                />
              )}
              <span
                className={classNames(
                  "rounded-full px-1.5 text-[11px] tabular-nums",
                  active ? "bg-brand-100 text-brand-700" : "bg-slate-100 text-slate-500",
                )}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* key by role+documentId so the panel refetches when role changes */}
      <DistributionPanel key={`${documentId}:${activeRole}`} role={activeRole} unit={unit} />
    </div>
  );
}

export default function StatsPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const navigate = useNavigate();
  const id = documentId ?? "";

  const doc = useApi(() => api.getDocument(id), [id]);
  const flags = useApi(() => api.listFlags(id), [id]);
  const fields = useApi(() => api.listFields(id), [id]);

  if (!documentId) {
    return (
      <ErrorBlock message="No document id in the URL." onRetry={() => navigate("/")} />
    );
  }

  const reviewHref = `/documents/${id}`;

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Link
            to={reviewHref}
            className="inline-flex items-center gap-1.5 font-medium text-slate-600 hover:text-brand-700"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to review
          </Link>
          <span className="text-slate-300">/</span>
          <Link to="/" className="inline-flex items-center gap-1 hover:text-slate-700">
            <Home className="h-3.5 w-3.5" />
            Documents
          </Link>
        </div>

        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            {doc.loading ? (
              <div className="h-9 w-64 animate-pulse rounded-md bg-slate-100" />
            ) : doc.data ? (
              <>
                <h1 className="flex flex-wrap items-center gap-x-3 gap-y-1 text-2xl font-bold tracking-tight text-slate-800">
                  <span className="font-mono text-brand-700">{doc.data.doc_no}</span>
                  {doc.data.title && (
                    <span className="truncate text-lg font-semibold text-slate-600">
                      {doc.data.title}
                    </span>
                  )}
                </h1>
                <p className="mt-1 text-sm text-slate-500">
                  Document analytics — validation flags and value distributions across{" "}
                  {doc.data.page_count} {doc.data.page_count === 1 ? "page" : "pages"} ·{" "}
                  {doc.data.n_fields} fields.
                </p>
              </>
            ) : (
              <h1 className="text-2xl font-bold tracking-tight text-slate-800">Document stats</h1>
            )}
          </div>
          <Link to={reviewHref} className="btn-secondary shrink-0">
            <ListChecks className="h-4 w-4" />
            Review queue
          </Link>
        </div>
      </div>

      {/* Flags dashboard */}
      <section className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <ListChecks className="h-5 w-5 text-brand-600" />
          <h2 className="text-base font-semibold text-slate-800">Validation flags</h2>
        </div>
        {flags.loading ? (
          <LoadingBlock label="Loading flags…" />
        ) : flags.error ? (
          <ErrorBlock message={flags.error} onRetry={flags.reload} />
        ) : (
          <FlagsDashboard flags={flags.data ?? []} />
        )}
      </section>

      {/* Distributions */}
      <section className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-5 w-5 text-brand-600" />
          <h2 className="text-base font-semibold text-slate-800">Value distributions</h2>
        </div>
        {fields.loading ? (
          <LoadingBlock label="Loading fields…" />
        ) : fields.error ? (
          <ErrorBlock message={fields.error} onRetry={fields.reload} />
        ) : (
          <DistributionsSection fields={fields.data ?? []} documentId={id} />
        )}
      </section>
    </div>
  );
}
