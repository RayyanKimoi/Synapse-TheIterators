"use client";

import { useMemo } from "react";

import { BudgetBurn } from "@/components/BudgetBurn";
import type { BudgetSample } from "@/lib/budget";
import type { WorkflowIR } from "@/lib/types";
import { cn } from "@/lib/utils";
import { nodeTelemetry, useTelemetryStore } from "@/store/useTelemetryStore";

/**
 * The analytics strip beneath the arena: what the two lanes did over the
 * course of a run, drawn rather than tabulated.
 *
 * Hand-rolled SVG rather than a charting dependency — three series on a
 * shared time axis is less code than configuring a library, and it keeps the
 * lines on the same lime-on-black ramp as the rest of the surface. The
 * compiled lane is always lime, the baseline always neutral grey, so the two
 * never swap identity between the arena and these charts.
 */

const W = 640;
const H = 170;
const PAD = { top: 14, right: 12, bottom: 20, left: 42 };

const LIME = "hsl(var(--stream))";
const GREY = "hsl(0 0% 58%)";

type Series = { label: string; stroke: string; points: [number, number][] };

function path(
  points: [number, number][],
  xScale: (value: number) => number,
  yScale: (value: number) => number,
) {
  if (points.length < 2) return "";
  return points
    .map(([x, y], index) => `${index ? "L" : "M"}${xScale(x).toFixed(1)},${yScale(y).toFixed(1)}`)
    .join(" ");
}

function LineChart({
  title,
  caption,
  series,
  formatY,
  emptyNote,
}: {
  title: string;
  caption: string;
  series: Series[];
  formatY: (value: number) => string;
  emptyNote: string;
}) {
  const maxX = Math.max(1, ...series.flatMap((s) => s.points.map(([x]) => x)));
  const maxY = Math.max(...series.flatMap((s) => s.points.map(([, y]) => y)), 0) || 1;
  const hasData = series.some((s) => s.points.length > 1);

  const xScale = (value: number) => PAD.left + (value / maxX) * (W - PAD.left - PAD.right);
  const yScale = (value: number) =>
    H - PAD.bottom - (value / maxY) * (H - PAD.top - PAD.bottom);

  const ticks = [0, 0.25, 0.5, 0.75, 1];

  return (
    <figure className="void-card void-card-hover min-w-0 rounded-2xl p-4">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-head text-[13px] font-semibold tracking-tight text-white">{title}</h3>
          <p className="mt-1 truncate font-sans text-[11px] text-white/45">{caption}</p>
        </div>
        <ul className="flex shrink-0 items-center gap-3">
          {series.map((s) => (
            <li
              key={s.label}
              className="flex items-center gap-1.5 font-sans text-[10.5px] text-white/60"
            >
              <span
                aria-hidden
                className="h-[2px] w-4 rounded-full"
                style={{
                  background: s.stroke,
                  boxShadow: s.stroke === LIME ? "0 0 8px hsl(var(--stream))" : undefined,
                }}
              />
              {s.label}
            </li>
          ))}
        </ul>
      </figcaption>

      <div className="relative mt-3">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="h-[170px] w-full"
          role="img"
          aria-label={`${title}. ${caption}`}
          preserveAspectRatio="none"
        >
          {/* Gridlines carry their own value, so the shape reads without a
              hover target. */}
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={PAD.left}
                x2={W - PAD.right}
                y1={yScale(maxY * tick)}
                y2={yScale(maxY * tick)}
                stroke="hsl(83 40% 50% / 0.1)"
                strokeWidth={1}
              />
              <text
                x={PAD.left - 6}
                y={yScale(maxY * tick) + 3}
                textAnchor="end"
                className="fill-white/35 font-sans"
                style={{ fontSize: 8.5 }}
              >
                {formatY(maxY * tick)}
              </text>
            </g>
          ))}

          <line
            x1={PAD.left}
            x2={W - PAD.right}
            y1={H - PAD.bottom}
            y2={H - PAD.bottom}
            stroke="hsl(0 0% 100% / 0.14)"
          />

          {series.map((s) => {
            const d = path(s.points, xScale, yScale);
            if (!d) return null;
            const lit = s.stroke === LIME;
            const last = s.points[s.points.length - 1];
            return (
              <g key={s.label}>
                {lit && (
                  <path
                    d={`${d} L${xScale(last[0]).toFixed(1)},${H - PAD.bottom} L${xScale(
                      s.points[0][0],
                    ).toFixed(1)},${H - PAD.bottom} Z`}
                    fill="hsl(var(--stream) / 0.1)"
                    stroke="none"
                  />
                )}
                <path
                  d={d}
                  fill="none"
                  stroke={s.stroke}
                  strokeWidth={lit ? 2 : 1.5}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  strokeDasharray={lit ? undefined : "4 3"}
                  style={
                    lit ? { filter: "drop-shadow(0 0 6px hsl(var(--stream) / 0.65))" } : undefined
                  }
                />
                <circle cx={xScale(last[0])} cy={yScale(last[1])} r={2.6} fill={s.stroke} />
              </g>
            );
          })}

          <text x={PAD.left} y={H - 6} className="fill-white/30 font-sans" style={{ fontSize: 8.5 }}>
            0 ms
          </text>
          <text
            x={W - PAD.right}
            y={H - 6}
            textAnchor="end"
            className="fill-white/30 font-sans"
            style={{ fontSize: 8.5 }}
          >
            {Math.round(maxX)} ms
          </text>
        </svg>

        {!hasData && (
          <p className="pointer-events-none absolute inset-0 flex items-center justify-center font-sans text-[11px] text-white/35">
            {emptyNote}
          </p>
        )}
      </div>
    </figure>
  );
}

/** Per-agent compiled latency: where the time that is left actually goes. */
function NodeLatencyChart({ workflow }: { workflow: WorkflowIR }) {
  const compiled = useTelemetryStore((state) => state.runs.compiled);

  const bars = workflow.nodes.map((node) => {
    const telemetry = nodeTelemetry(compiled, node.id);
    return {
      id: node.id,
      label: node.persona ?? node.id,
      ms: telemetry.latency_ms ?? 0,
      cached: Boolean(telemetry.is_cache_hit),
    };
  });

  const max = Math.max(1, ...bars.map((bar) => bar.ms));

  return (
    <figure className="void-card void-card-hover min-w-0 rounded-2xl p-4">
      <figcaption>
        <h3 className="font-head text-[13px] font-semibold tracking-tight text-white">
          Latency by agent
        </h3>
        <p className="mt-1 font-sans text-[11px] text-white/45">
          Compiled lane · a solid bar ran, a hollow one came back from the cache
        </p>
      </figcaption>

      <ul className="mt-3.5 space-y-2">
        {bars.map((bar) => (
          <li key={bar.id} className="grid grid-cols-[120px_1fr_58px] items-center gap-2.5">
            <span className="truncate font-sans text-[11px] text-white/60" title={bar.label}>
              {bar.label}
            </span>
            <span className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
              <span
                className={cn(
                  "block h-full rounded-full transition-[width] duration-700 ease-out",
                  bar.cached
                    ? "bg-stream/25 shadow-[inset_0_0_0_1px_hsl(var(--stream)/0.6)]"
                    : "bg-stream shadow-[0_0_14px_-2px_hsl(var(--stream)/0.9)]",
                )}
                style={{ width: `${bar.ms > 0 ? Math.max(3, (bar.ms / max) * 100) : 0}%` }}
              />
            </span>
            <span className="tabular text-right font-sans text-[11px] text-white/70">
              {bar.ms > 0 ? `${Math.round(bar.ms)}ms` : "—"}
            </span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

const toPoints = (samples: BudgetSample[], key: "costUsd" | "tokens"): [number, number][] =>
  samples.map((sample) => [sample.t, sample[key]]);

export function AnalyticsCharts({ workflow }: { workflow: WorkflowIR }) {
  const runs = useTelemetryStore((state) => state.runs);

  const spend = useMemo<Series[]>(
    () => [
      { label: "Baseline", stroke: GREY, points: toPoints(runs.baseline.samples, "costUsd") },
      { label: "Compiled", stroke: LIME, points: toPoints(runs.compiled.samples, "costUsd") },
    ],
    [runs.baseline.samples, runs.compiled.samples],
  );

  const tokens = useMemo<Series[]>(
    () => [
      { label: "Baseline", stroke: GREY, points: toPoints(runs.baseline.samples, "tokens") },
      { label: "Compiled", stroke: LIME, points: toPoints(runs.compiled.samples, "tokens") },
    ],
    [runs.baseline.samples, runs.compiled.samples],
  );

  return (
    <section aria-label="Run analytics" className="grid gap-3 lg:grid-cols-2">
      <LineChart
        title="Spend over the run"
        caption="Cumulative USD against elapsed pipeline time"
        series={spend}
        formatY={(value) => `$${value.toFixed(4)}`}
        emptyNote="Run the arena to plot spend"
      />
      <LineChart
        title="Tokens over the run"
        caption="Cumulative prompt + completion tokens"
        series={tokens}
        formatY={(value) =>
          value >= 1000 ? `${(value / 1000).toFixed(1)}k` : String(Math.round(value))
        }
        emptyNote="Run the arena to plot token burn"
      />
      <NodeLatencyChart workflow={workflow} />
      <BudgetBurn declaredBudget={workflow.budget_limit_usd} />
    </section>
  );
}
