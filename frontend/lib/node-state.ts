import type { NodeStatus } from "./types";

/** Visual vocabulary for the five node states (PRD 8.1). */
export const STATE_STYLE: Record<
  NodeStatus,
  { label: string; border: string; text: string; glow: string; edge: string }
> = {
  IDLE: {
    label: "Idle",
    border: "border-border",
    text: "text-muted-foreground",
    glow: "",
    edge: "hsl(240 5% 26%)",
  },
  RUNNING: {
    label: "Running",
    border: "border-state-running",
    text: "text-state-running",
    glow: "shadow-[0_0_22px_-2px_hsl(var(--state-running)/0.65)]",
    edge: "hsl(189 94% 43%)",
  },
  CACHED: {
    label: "Cached",
    border: "border-state-cached",
    text: "text-state-cached",
    glow: "shadow-[0_0_26px_-2px_hsl(var(--state-cached)/0.75)]",
    edge: "hsl(160 84% 39%)",
  },
  COMPLETED: {
    label: "Completed",
    border: "border-state-completed",
    text: "text-state-completed",
    glow: "",
    edge: "hsl(258 90% 66%)",
  },
  FAILED: {
    label: "Failed",
    border: "border-state-failed",
    text: "text-state-failed",
    glow: "shadow-[0_0_22px_-2px_hsl(var(--state-failed)/0.6)]",
    edge: "hsl(0 84% 60%)",
  },
};
