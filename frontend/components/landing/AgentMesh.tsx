"use client";

import { CircuitBoard } from "@/components/ui/circuit-board";

/**
 * Hero right: the compiled case. One machine, six agent nodes dispatched off a
 * single scheduler and converging on one merge, every trace live at once.
 *
 * Node coordinates are plain pixels inside the board's width/height box.
 */

const W = 560;
const H = 248;

const LANES = [
  { id: "a1", y: 44, label: "retrieve" },
  { id: "a2", y: 84, label: "rank" },
  { id: "a3", y: 124, label: "summarise" },
  { id: "a4", y: 164, label: "verify" },
  { id: "a5", y: 204, label: "price" },
];

const LANE_X = 280;

const nodes = [
  { id: "sched", x: 78, y: 124, label: "Scheduler", status: "active" as const, size: "lg" as const },
  ...LANES.map((lane) => ({
    id: lane.id,
    x: LANE_X,
    y: lane.y,
    status: "processing" as const,
    size: "sm" as const,
  })),
  { id: "merge", x: 482, y: 124, label: "Merge", status: "active" as const, size: "lg" as const },
];

const connections = [
  ...LANES.map((lane) => ({ from: "sched", to: lane.id, animated: true })),
  ...LANES.map((lane) => ({ from: lane.id, to: "merge", animated: true })),
];

export function AgentMesh() {
  return (
    <div className="relative">
      <CircuitBoard
        nodes={nodes}
        connections={connections}
        width={W}
        height={H}
        variant="dark"
        gridSize={20}
        showGrid
        gridColor="hsl(83 78% 55% / 0.07)"
        traceColor="hsl(83 78% 55% / 0.26)"
        pulseColor="#a3e635"
        nodeColor="#a3e635"
        pulseSpeed={1.7}
        traceWidth={1.6}
        className="mx-auto max-w-full"
      />

      {/* Lane names, beside their nodes rather than under them. */}
      <div className="pointer-events-none absolute inset-0 mx-auto" style={{ width: W, height: H }}>
        {LANES.map((lane) => (
          <span
            key={lane.id}
            className="absolute rounded bg-void/90 px-1.5 py-1 font-sans text-[11px] leading-none text-white/60"
            style={{ left: LANE_X + 20, top: lane.y - 9 }}
          >
            {lane.label}
          </span>
        ))}
      </div>
      <p className="sr-only">
        A single machine running six agent nodes concurrently: one scheduler dispatches five
        workers — retrieve, rank, summarise, verify and price — which all converge on one merge
        node.
      </p>
    </div>
  );
}
