import type { NodeStatus } from "./types";

/** Visual vocabulary for the five node states (PRD 8.1). */
export const STATE_STYLE: Record<
  NodeStatus,
  {
    label: string;
    border: string;
    text: string;
    glow: string;
    edge: string;
    /** Tailwind background for the small status dot. */
    dot: string;
    /** Inner hairline + tint applied to the node card body. */
    tint: string;
  }
> = {
  IDLE: {
    label: "Idle",
    border: "border-white/[0.07]",
    text: "text-muted-foreground",
    glow: "",
    edge: "hsl(240 5% 26%)",
    dot: "bg-state-idle",
    tint: "",
  },
  RUNNING: {
    label: "Running",
    border: "border-state-running/80",
    text: "text-state-running",
    glow: "shadow-[0_0_34px_-6px_hsl(var(--state-running)/0.85),inset_0_1px_0_hsl(0_0%_100%/0.08)]",
    edge: "hsl(189 94% 43%)",
    dot: "bg-state-running",
    tint: "bg-[radial-gradient(120%_80%_at_50%_0%,hsl(189_94%_43%/0.14),transparent_70%)]",
  },
  CACHED: {
    label: "Cache hit",
    border: "border-state-cached/85",
    text: "text-state-cached",
    glow: "shadow-[0_0_38px_-6px_hsl(var(--state-cached)/0.95),inset_0_1px_0_hsl(0_0%_100%/0.08)]",
    edge: "hsl(160 84% 39%)",
    dot: "bg-state-cached",
    tint: "bg-[radial-gradient(120%_80%_at_50%_0%,hsl(160_84%_39%/0.18),transparent_70%)]",
  },
  COMPLETED: {
    label: "Completed",
    border: "border-state-completed/70",
    text: "text-state-completed",
    glow: "shadow-[inset_0_1px_0_hsl(0_0%_100%/0.06)]",
    edge: "hsl(258 90% 66%)",
    dot: "bg-state-completed",
    tint: "",
  },
  FAILED: {
    label: "Failed",
    border: "border-state-failed/85",
    text: "text-state-failed",
    glow: "shadow-[0_0_30px_-6px_hsl(var(--state-failed)/0.8)]",
    edge: "hsl(0 84% 60%)",
    dot: "bg-state-failed",
    tint: "bg-[radial-gradient(120%_80%_at_50%_0%,hsl(0_84%_60%/0.14),transparent_70%)]",
  },
};

/** The baseline lane is deliberately styled as blocked, not optimized. */
export const BLOCKING_EDGE = "hsl(25 95% 53%)";
