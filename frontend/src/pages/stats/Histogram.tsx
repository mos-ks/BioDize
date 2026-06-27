// Hand-rolled SVG histogram for a role's value distribution.
// No charting library — pure SVG bars scaled to the tallest bin.

import { useId, useState } from "react";
import type { HistogramBin } from "../../api/types";
import { classNames } from "../../lib/ui";

/** Trim long floats but keep meaningful precision for axis labels. */
function fmtNum(n: number): string {
  if (!Number.isFinite(n)) return "—";
  const abs = Math.abs(n);
  let s: string;
  if (abs !== 0 && (abs < 0.001 || abs >= 1e6)) {
    s = n.toExponential(2);
  } else {
    s = n.toFixed(Math.abs(n % 1) < 1e-9 ? 0 : 2);
  }
  return s;
}

export function Histogram({
  bins,
  unit,
  min,
  max,
  mark,
}: {
  bins: HistogramBin[];
  unit?: string | null;
  min?: number | null;
  max?: number | null;
  /** Draw a vertical marker at this value (e.g. the field being reviewed). */
  mark?: number | null;
}) {
  const clipId = useId();
  const [hover, setHover] = useState<number | null>(null);

  const width = 640;
  const height = 220;
  const padTop = 16;
  const padBottom = 28;
  const padX = 8;
  const plotW = width - padX * 2;
  const plotH = height - padTop - padBottom;

  const maxCount = Math.max(1, ...bins.map((b) => b.count));
  const totalCount = bins.reduce((acc, b) => acc + b.count, 0);
  const n = bins.length;
  const gap = n > 24 ? 1 : 3;
  const slot = plotW / n;
  // Cap bar width when there are very few bins, so a single / degenerate
  // distribution (e.g. all values equal) renders as a neat centered column
  // instead of one full-width block.
  const maxBarW = n <= 2 ? 110 : slot - gap;
  const barW = Math.max(1, Math.min(slot - gap, maxBarW));

  const axisMin = min ?? (bins.length ? bins[0].start : 0);
  const axisMax = max ?? (bins.length ? bins[bins.length - 1].end : 0);

  return (
    <div className="w-full">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        style={{ height: 200 }}
        role="img"
        aria-label="Value distribution histogram"
        preserveAspectRatio="none"
      >
        <defs>
          <clipPath id={clipId}>
            <rect x="0" y="0" width={width} height={height} rx="6" />
          </clipPath>
        </defs>

        {/* baseline */}
        <line
          x1={padX}
          x2={width - padX}
          y1={padTop + plotH}
          y2={padTop + plotH}
          stroke="#e2e8f0"
          strokeWidth={1}
        />

        <g clipPath={`url(#${clipId})`}>
          {bins.map((b, i) => {
            const h = (b.count / maxCount) * plotH;
            const y = padTop + (plotH - h);
            const active = hover === i;
            return (
              <g key={i}>
                {/* invisible full-height hit target for easier hover */}
                <rect
                  x={padX + i * slot}
                  y={padTop}
                  width={slot}
                  height={plotH}
                  fill="transparent"
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover((c) => (c === i ? null : c))}
                />
                <rect
                  x={padX + i * slot + (slot - barW) / 2}
                  y={b.count === 0 ? padTop + plotH - 1 : y}
                  width={barW}
                  height={b.count === 0 ? 1 : Math.max(1, h)}
                  rx={barW > 6 ? 2 : 0.5}
                  className={classNames(
                    "transition-colors",
                    b.count === 0
                      ? "fill-slate-200"
                      : active
                        ? "fill-brand-600"
                        : "fill-brand-500",
                  )}
                  pointerEvents="none"
                />
              </g>
            );
          })}
        </g>

        {/* marker for the value under review */}
        {mark != null && Number.isFinite(mark) && axisMax > axisMin && (() => {
          const mx = Math.max(
            padX,
            Math.min(width - padX, padX + ((mark - axisMin) / (axisMax - axisMin)) * plotW),
          );
          return (
            <g pointerEvents="none">
              <line x1={mx} x2={mx} y1={padTop} y2={padTop + plotH} stroke="#f43f5e" strokeWidth={2} strokeDasharray="4 2" />
              <polygon points={`${mx - 5},${padTop} ${mx + 5},${padTop} ${mx},${padTop + 7}`} fill="#f43f5e" />
            </g>
          );
        })()}
      </svg>

      {/* axis labels */}
      <div className="mt-1 flex items-center justify-between px-1 text-[11px] tabular-nums text-slate-400">
        <span>
          {fmtNum(axisMin)}
          {unit ? ` ${unit}` : ""}
        </span>
        <span className="text-slate-300">
          {hover != null && bins[hover] ? (
            <span className="font-medium text-slate-500">
              {fmtNum(bins[hover].start)}–{fmtNum(bins[hover].end)}
              {unit ? ` ${unit}` : ""} · {bins[hover].count}{" "}
              {bins[hover].count === 1 ? "value" : "values"}
            </span>
          ) : (
            <>
              {totalCount} {totalCount === 1 ? "value" : "values"} · {n} bins
            </>
          )}
        </span>
        <span>
          {fmtNum(axisMax)}
          {unit ? ` ${unit}` : ""}
        </span>
      </div>
    </div>
  );
}

export { fmtNum };
