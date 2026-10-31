"use client";

import { useEffect, useRef } from "react";

import { prefersReducedMotion } from "@/hooks/useCountUp";
import { RACK_LABEL, RACK_MODEL, RACK_SVG } from "./rack-figure";

/**
 * The right-rail terminal block: an isometric figure (anatomy skill) of one
 * chassis running six agent cards. Pull the lever and more lanes go in flight;
 * the dial reads what is left of the critical path.
 *
 * Parts are moved by writing attributes on refs, never by re-rendering.
 */

const M = RACK_MODEL;
const C = M.camera;

const isoAt = ([x, y, z]: [number, number, number]) => [
  C.origin[0] + (x * C.sinA - y * C.cosA) * C.k,
  C.origin[1] + ((x * C.cosA + y * C.sinA) * C.sinE - z * C.cosE) * C.k,
];

const ORIGIN = isoAt([0, 0, 0]);

const shift = (by: [number, number, number]) => {
  const to = isoAt(by);
  return `translate(${(to[0] - ORIGIN[0]).toFixed(2)} ${(to[1] - ORIGIN[1]).toFixed(2)})`;
};

const needleAt = (turn: number) => {
  const angle = turn * Math.PI * 2;
  const [cx, cy] = M.needle.dial;
  const from = isoAt([cx - Math.sin(angle) * M.needle.hub, cy + Math.cos(angle) * M.needle.hub, M.needle.top]);
  const to = isoAt([cx + Math.sin(angle) * M.needle.tip, cy - Math.cos(angle) * M.needle.tip, M.needle.top]);
  return `M${from[0].toFixed(1)} ${from[1].toFixed(1)}L${to[0].toFixed(1)} ${to[1].toFixed(1)}`;
};

/** Two measured runs, linear between them — the same model that moves the parts. */
const pathFor = (lanes: number) =>
  M.path.cold - ((M.path.cold - M.path.warm) * (lanes - 1)) / (M.cards - 1);

const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));
const ms = (value: number) => `${Math.round(value).toLocaleString("en-US")} ms`;

export function AgentRack() {
  const stage = useRef<HTMLDivElement | null>(null);
  const lanesOut = useRef<HTMLSpanElement | null>(null);
  const pathOut = useRef<HTMLSpanElement | null>(null);
  const savedOut = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    const host = stage.current;
    if (!host) return;
    const svg = host.querySelector("svg");
    if (!svg) return;

    const carriage = svg.querySelector<SVGGElement>('[data-part="carriage"]');
    const needle = svg.querySelector<SVGPathElement>('[data-part="needle"]');
    const flags = Array.from(svg.querySelectorAll<SVGGElement>('[data-part="flag"]'));
    const lamps = Array.from(svg.querySelectorAll<SVGGElement>('[data-part="led"],[data-part="lane"]'));
    const calm = prefersReducedMotion();

    let x = M.detents[0];
    let target = M.detents[M.cards - 1];
    let shown = -1;
    let raf = 0;
    let last = 0;
    let visible = false;
    let touring = !calm;
    let clock = 0;
    let idle = 0;

    const laneAt = (position: number) => {
      let best = 0;
      for (let index = 1; index < M.detents.length; index++) {
        if (Math.abs(M.detents[index] - position) < Math.abs(M.detents[best] - position)) best = index;
      }
      return best + 1;
    };

    function draw() {
      carriage?.setAttribute("transform", shift([x, 0, 0]));
      const lanes = laneAt(x);
      needle?.setAttribute("d", needleAt(((lanes - 1) / (M.cards - 1)) * 0.75));
      for (const flag of flags) {
        const on = Number(flag.dataset.lane) < lanes;
        flag.setAttribute("transform", shift([0, 0, on ? 0 : -M.flagLift]));
      }
      for (const lamp of lamps) {
        lamp.style.opacity = Number(lamp.dataset.lane) < lanes ? "1" : "0.1";
      }
      if (lanes === shown) return;
      shown = lanes;
      const path = pathFor(lanes);
      if (lanesOut.current) lanesOut.current.textContent = String(lanes);
      if (pathOut.current) pathOut.current.textContent = ms(path);
      if (savedOut.current) {
        savedOut.current.textContent = `${(((M.path.cold - path) / M.path.cold) * 100).toFixed(1)}%`;
      }
      host?.setAttribute("aria-valuenow", String(lanes));
      host?.setAttribute("aria-valuetext", `${lanes} of ${M.cards} lanes in flight, ${ms(path)} critical path`);
    }

    function tick(now: number) {
      const dt = last ? Math.min((now - last) / 1000, 1 / 30) : 1 / 60;
      last = now;
      if (touring) {
        clock += dt;
        // Walk up the lanes, hold at six, drop back.
        const step = Math.floor(clock / 1.1) % (M.cards + 2);
        target = M.detents[Math.min(step, M.cards - 1)];
      }
      x = calm ? target : x + (target - x) * (1 - Math.exp(-dt / 0.2));
      if (Math.abs(target - x) < 0.02) x = target;
      draw();
      const settled = !touring && x === target;
      raf = visible && !settled ? requestAnimationFrame(tick) : 0;
    }

    const run = () => {
      if (!raf && visible) {
        last = 0;
        raf = requestAnimationFrame(tick);
      }
    };

    const steer = (next: number) => {
      touring = false;
      target = clamp(next, M.reach[0], M.reach[1]);
      window.clearTimeout(idle);
      idle = window.setTimeout(() => {
        touring = !calm;
        clock = 0;
        run();
      }, 3200);
      run();
    };

    const onMove = (event: PointerEvent) => {
      const box = svg.getBoundingClientRect();
      const share = clamp((event.clientX - box.left) / box.width, 0, 1);
      steer(M.reach[0] + share * (M.reach[1] - M.reach[0]));
    };

    const onKey = (event: KeyboardEvent) => {
      const here = laneAt(target);
      let to: number | null = null;
      if (event.key === "ArrowRight" || event.key === "ArrowUp") to = Math.min(M.cards, here + 1);
      if (event.key === "ArrowLeft" || event.key === "ArrowDown") to = Math.max(1, here - 1);
      if (event.key === "Home") to = 1;
      if (event.key === "End") to = M.cards;
      if (to === null) return;
      event.preventDefault();
      steer(M.detents[to - 1]);
    };

    const watcher = new IntersectionObserver(
      (entries) => {
        visible = entries[entries.length - 1].isIntersecting;
        if (visible) run();
      },
      { rootMargin: "120px 0px" },
    );
    watcher.observe(host);

    host.addEventListener("pointermove", onMove);
    host.addEventListener("keydown", onKey);
    draw();

    return () => {
      watcher.disconnect();
      cancelAnimationFrame(raf);
      window.clearTimeout(idle);
      host.removeEventListener("pointermove", onMove);
      host.removeEventListener("keydown", onKey);
    };
  }, []);

  return (
    <div className="iso rack glass glass-lime relative overflow-hidden rounded-2xl border border-white/[0.06] bg-black/40 p-4 sm:p-5">
      <div className="flex items-baseline justify-between font-sans text-[10px] uppercase tracking-[0.22em] text-white/55">
        <span>Fig 1 · Execution engine</span>
        <span className="stream-text">Live</span>
      </div>

      <div
        ref={stage}
        tabIndex={0}
        role="slider"
        aria-label="Agent rack: arrow keys open and close execution lanes"
        aria-valuemin={1}
        aria-valuemax={M.cards}
        aria-valuenow={M.cards}
        className="mx-auto mt-3 max-w-[94%] cursor-ew-resize outline-none ring-offset-4 ring-offset-black focus-visible:ring-2 focus-visible:ring-stream"
        dangerouslySetInnerHTML={{ __html: RACK_SVG }}
      />

      <dl className="mt-4 grid grid-cols-3 gap-px overflow-hidden rounded-xl border border-white/[0.07] bg-white/[0.04] font-sans">
        {[
          { label: "In flight", ref: lanesOut, value: String(M.cards), lime: true },
          { label: "Critical path", ref: pathOut, value: ms(M.path.warm), lime: false },
          { label: "Off baseline", ref: savedOut, value: "57.9%", lime: true },
        ].map((cell) => (
          <div key={cell.label} className="bg-black/70 px-3 py-2">
            <dt className="text-[9.5px] uppercase tracking-[0.18em] text-white/55">{cell.label}</dt>
            <dd
              className={`tabular mt-1 text-[15px] leading-none ${cell.lime ? "stream-text" : "text-white/85"}`}
            >
              <span ref={cell.ref}>{cell.value}</span>
            </dd>
          </div>
        ))}
      </dl>

      <p className="mt-3 font-sans text-[12px] text-white/50">Drag across the figure to open lanes.</p>
      <span className="sr-only">{RACK_LABEL}</span>
    </div>
  );
}
