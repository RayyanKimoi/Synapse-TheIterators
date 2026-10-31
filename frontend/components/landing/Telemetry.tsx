"use client";

import { useEffect, useRef, useState } from "react";

import { prefersReducedMotion, useCountUp } from "@/hooks/useCountUp";

/**
 * Telemetry for the landing page.
 *
 * Form follows the data's job, not decoration:
 *  - headline numbers  -> KPI row of stat tiles (no chart)
 *  - one ratio vs a limit -> meter, accent fill on a lighter step of the same ramp
 *  - baseline vs compiled -> *emphasis*: the compiled bar carries the hue, the
 *    baseline is context grey. Two categories of one measure, so direct labels
 *    and no legend.
 *
 * Every figure below is a measured run recorded in CLAUDE_UPDATE.md. Nothing is
 * a generated series — where we have no history, there is no sparkline.
 */

const BASELINE_MS = 35000;
const COMPILED_MS = 14730;

/** Fires once when the block reaches the viewport, so numbers resolve on arrival. */
function useArmed<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [armed, setArmed] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (prefersReducedMotion()) {
      setArmed(true);
      return;
    }
    const watcher = new IntersectionObserver(
      (entries) => {
        if (!entries[entries.length - 1].isIntersecting) return;
        setArmed(true);
        watcher.disconnect();
      },
      { threshold: 0.25 },
    );
    watcher.observe(node);
    return () => watcher.disconnect();
  }, []);

  return { ref, armed };
}

const pct = (n: number) => `${n.toFixed(1)}%`;
const thousands = (n: number) => Math.round(n).toLocaleString("en-US");
const seconds = (n: number) => `${n.toFixed(2)}`;

type TileProps = {
  label: string;
  value: number;
  format: (n: number) => string;
  unit?: string;
  delta: string;
  armed: boolean;
};

/** label · value · delta. No trend line: we have no run history to draw one from. */
function StatTile({ label, value, format, unit, delta, armed }: TileProps) {
  const ref = useCountUp(armed ? value : 0, format, 1.1);
  return (
    <div className="bg-void p-5">
      <p className="font-sans text-[12px] leading-none text-white/55">{label}</p>
      <p className="mt-3 flex items-baseline gap-1 text-white">
        <span ref={ref} className="font-head text-[30px] font-semibold leading-none tracking-tight">
          {format(0)}
        </span>
        {unit && <span className="font-sans text-[13px] text-white/55">{unit}</span>}
      </p>
      <p className="stream-text mt-2 font-sans text-[11.5px] leading-tight">{delta}</p>
    </div>
  );
}

/** Accent fill on a lighter step of the same ramp, so state reads across the bar. */
function Meter({
  label,
  value,
  max,
  caption,
  armed,
}: {
  label: string;
  value: number;
  max: number;
  caption: string;
  armed: boolean;
}) {
  const share = Math.max(0, Math.min(1, value / max));
  return (
    <div className="bg-void p-5">
      <div className="flex items-baseline justify-between gap-3">
        <p className="font-sans text-[12px] leading-none text-white/55">{label}</p>
        <p className="font-head text-[14px] font-semibold leading-none text-white">
          {value} <span className="text-white/45">/ {max}</span>
        </p>
      </div>
      <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-stream/15">
        <div
          className="h-full rounded-full bg-stream transition-[width] duration-[1100ms] ease-out"
          style={{ width: armed ? `${share * 100}%` : "0%" }}
        />
      </div>
      <p className="mt-2 font-sans text-[11.5px] leading-tight text-white/50">{caption}</p>
    </div>
  );
}

/**
 * Emphasis, not categorical: the compiled run is the point and the baseline is
 * context. 4px rounded ends, direct labels, no legend for a single measure.
 */
function CriticalPath({ armed }: { armed: boolean }) {
  const rows = [
    { name: "Sequential baseline", ms: BASELINE_MS, accent: false },
    { name: "SYNAPSE compiled", ms: COMPILED_MS, accent: true },
  ];
  return (
    <div className="bg-void p-5 sm:col-span-2">
      <p className="font-sans text-[12px] leading-none text-white/55">
        Critical path, same workflow
      </p>
      <div className="mt-4 space-y-3">
        {rows.map((row) => (
          <div key={row.name}>
            <div className="flex items-baseline justify-between gap-3">
              <span className="font-sans text-[12px] text-white/70">{row.name}</span>
              <span
                className={`tabular font-head text-[13px] font-semibold ${
                  row.accent ? "stream-text" : "text-white/60"
                }`}
              >
                {thousands(row.ms)} ms
              </span>
            </div>
            <div className="mt-1.5 h-2.5 w-full">
              <div
                className={`h-full rounded transition-[width] duration-[1200ms] ease-out ${
                  row.accent ? "bg-stream" : "bg-white/20"
                }`}
                style={{ width: armed ? `${(row.ms / BASELINE_MS) * 100}%` : "0%" }}
              />
            </div>
          </div>
        ))}
      </div>
      <p className="mt-4 font-sans text-[11.5px] leading-relaxed text-white/50">
        Both lanes run the same engine over the same graph — one as a chain, one as the compiled
        dependency tree.
      </p>
    </div>
  );
}

export function Telemetry() {
  const { ref, armed } = useArmed<HTMLDivElement>();

  return (
    <div
      ref={ref}
      className="grid gap-px overflow-hidden rounded-2xl border border-white/[0.08] bg-white/[0.07] sm:grid-cols-2 lg:grid-cols-4"
    >
      <CriticalPath armed={armed} />
      <StatTile
        label="Latency eliminated"
        value={57.9}
        format={pct}
        delta="20,270 ms off the critical path"
        armed={armed}
      />
      <StatTile
        label="Fusion hit rate"
        value={66.7}
        format={pct}
        delta="2 of 3 runs merge into one call"
        armed={armed}
      />
      <Meter
        label="Lanes in flight"
        value={6}
        max={6}
        caption="Ready-node dispatch, bounded by max_concurrent_tasks"
        armed={armed}
      />
      <StatTile
        label="Cache stall ceiling"
        value={1.52}
        format={seconds}
        unit="s"
        delta="Down from 14.76 s once every call was capped"
        armed={armed}
      />
      <StatTile
        label="Backend tests passing"
        value={118}
        format={thousands}
        delta="Zero mock multipliers left on the execution path"
        armed={armed}
      />
      <StatTile
        label="Planner vs. the clock"
        value={0.2}
        format={pct}
        delta="Projection agreed with the measured run"
        armed={armed}
      />
    </div>
  );
}
