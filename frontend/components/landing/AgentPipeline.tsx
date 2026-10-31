"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";

import { prefersReducedMotion } from "@/hooks/useCountUp";

/**
 * Hero left: one agent draining a queue.
 *
 * Tasks enter from the left, the agent admits exactly one at a time, holds it
 * while the core works, then emits a result. It is the sequential case — the
 * counterpart to the concurrent mesh on the right — and the animation is the
 * argument, not decoration.
 *
 * GSAP only: the PRD's animation mandate.
 */

const W = 520;
const H = 236;

const LANE_Y = H / 2;
const QUEUE_X = 52;
const AGENT_X = 260;
const OUT_X = 468;
const TASKS = 5;

const TASK_LABELS = ["fetch", "rank", "draft", "verify", "emit"];

export function AgentPipeline() {
  const root = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    const svg = root.current;
    if (!svg) return;
    if (prefersReducedMotion()) return;

    const ctx = gsap.context(() => {
      const timeline = gsap.timeline({ repeat: -1, paused: true });

      for (let index = 0; index < TASKS; index++) {
        const chip = `[data-task="${index}"]`;
        const at = index * 1.5;

        // Queue -> agent intake.
        timeline.fromTo(
          chip,
          { x: 0, opacity: 0 },
          { opacity: 1, duration: 0.25, ease: "power2.out" },
          at,
        );
        timeline.to(chip, { x: AGENT_X - QUEUE_X - 26, duration: 0.55, ease: "power2.inOut" }, at + 0.25);

        // The agent holds it while the core works.
        timeline.to(chip, { opacity: 0, duration: 0.18 }, at + 0.8);
        timeline.fromTo(
          "[data-core]",
          { scale: 1, transformOrigin: "center" },
          { scale: 1.22, duration: 0.3, yoyo: true, repeat: 1, ease: "sine.inOut" },
          at + 0.82,
        );
        timeline.fromTo(
          "[data-halo]",
          { opacity: 0.25, scale: 0.9, transformOrigin: "center" },
          { opacity: 0.75, scale: 1.25, duration: 0.42, yoyo: true, repeat: 1, ease: "sine.out" },
          at + 0.82,
        );

        // Result leaves on the output rail.
        timeline.fromTo(
          `[data-result="${index}"]`,
          { x: 0, opacity: 0 },
          { opacity: 1, duration: 0.2 },
          at + 1.18,
        );
        timeline.to(
          `[data-result="${index}"]`,
          { x: OUT_X - AGENT_X - 30, duration: 0.6, ease: "power2.in" },
          at + 1.22,
        );
        timeline.to(`[data-result="${index}"]`, { opacity: 0, duration: 0.2 }, at + 1.68);

        // The depth gauge fills one notch per completed task.
        timeline.to(
          "[data-fill]",
          { attr: { width: ((index + 1) / TASKS) * 150 }, duration: 0.4, ease: "power2.out" },
          at + 1.2,
        );
      }

      timeline.to("[data-fill]", { attr: { width: 0 }, duration: 0.3 }, TASKS * 1.5);

      const watcher = new IntersectionObserver(
        (entries) => {
          if (entries[entries.length - 1].isIntersecting) timeline.play();
          else timeline.pause();
        },
        { rootMargin: "80px 0px" },
      );
      watcher.observe(svg);
      return () => watcher.disconnect();
    }, svg);

    return () => ctx.revert();
  }, []);

  return (
    <svg
      ref={root}
      viewBox={`0 0 ${W} ${H}`}
      className="h-full w-full"
      role="img"
      aria-label="A single agent admitting one queued task at a time, working it, and emitting a result"
    >
      <defs>
        <linearGradient id="pipe-rail" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="hsl(var(--stream))" stopOpacity="0.05" />
          <stop offset="50%" stopColor="hsl(var(--stream))" stopOpacity="0.35" />
          <stop offset="100%" stopColor="hsl(var(--stream))" stopOpacity="0.05" />
        </linearGradient>
        <radialGradient id="pipe-halo">
          <stop offset="0%" stopColor="hsl(var(--stream))" stopOpacity="0.55" />
          <stop offset="70%" stopColor="hsl(var(--stream))" stopOpacity="0.08" />
          <stop offset="100%" stopColor="hsl(var(--stream))" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* The rail the whole pipeline sits on. */}
      <line x1={QUEUE_X} y1={LANE_Y} x2={OUT_X} y2={LANE_Y} stroke="url(#pipe-rail)" strokeWidth="2" />

      {/* Intake and output markers, so the rail ends on something. */}
      <circle cx={QUEUE_X} cy={LANE_Y} r="3.5" fill="hsl(var(--stream))" opacity="0.5" />
      <circle cx={OUT_X} cy={LANE_Y} r="3.5" fill="hsl(var(--stream))" opacity="0.5" />

      {/* Queue depth gauge. */}
      <g transform={`translate(${QUEUE_X - 8} ${LANE_Y + 50})`}>
        <rect width="150" height="5" rx="2.5" fill="hsl(var(--stream) / 0.12)" />
        <rect data-fill width="0" height="5" rx="2.5" fill="hsl(var(--stream))" opacity="0.85" />
        <text x="0" y="22" className="fill-white/45 font-sans" fontSize="10" letterSpacing="0.14em">
          QUEUE DRAINED
        </text>
      </g>

      {/* The agent. */}
      <g>
        <circle data-halo cx={AGENT_X} cy={LANE_Y} r="56" fill="url(#pipe-halo)" />
        <rect
          x={AGENT_X - 34}
          y={LANE_Y - 34}
          width="68"
          height="68"
          rx="18"
          fill="hsl(var(--void))"
          stroke="hsl(var(--stream) / 0.45)"
          strokeWidth="1.5"
        />
        <g data-core>
          <rect
            x={AGENT_X - 13}
            y={LANE_Y - 13}
            width="26"
            height="26"
            rx="7"
            fill="hsl(var(--stream) / 0.16)"
            stroke="hsl(var(--stream))"
            strokeWidth="1.5"
          />
          <circle cx={AGENT_X} cy={LANE_Y} r="3.5" fill="hsl(var(--stream))" />
        </g>
        <text
          x={AGENT_X}
          y={LANE_Y - 50}
          textAnchor="middle"
          className="fill-white/55 font-sans"
          fontSize="10"
          letterSpacing="0.18em"
        >
          AGENT · 1 SLOT
        </text>
      </g>

      {/* Queued tasks. */}
      {Array.from({ length: TASKS }).map((_, index) => (
        <g key={`task-${index}`} data-task={index} transform={`translate(${QUEUE_X + 6} ${LANE_Y - 11})`}>
          <rect
            width="54"
            height="22"
            rx="6"
            fill="hsl(var(--void))"
            stroke="hsl(var(--stream) / 0.5)"
            strokeWidth="1"
          />
          <text
            x="27"
            y="15"
            textAnchor="middle"
            className="fill-white/75 font-sans"
            fontSize="9.5"
            letterSpacing="0.06em"
          >
            {TASK_LABELS[index]}
          </text>
        </g>
      ))}

      {/* Results leaving. */}
      {Array.from({ length: TASKS }).map((_, index) => (
        <g
          key={`result-${index}`}
          data-result={index}
          transform={`translate(${AGENT_X + 30} ${LANE_Y - 5})`}
          opacity="0"
        >
          <rect width="26" height="10" rx="5" fill="hsl(var(--stream))" opacity="0.9" />
        </g>
      ))}
    </svg>
  );
}
