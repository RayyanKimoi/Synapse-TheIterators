"use client";

import { memo, useEffect, useRef } from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import gsap from "gsap";
import { Bot, Wrench, Zap } from "lucide-react";

import { prefersReducedMotion } from "@/hooks/useCountUp";
import { STATE_STYLE } from "@/lib/node-state";
import type { NodeTelemetry, WorkflowNodeType } from "@/lib/types";
import { cn } from "@/lib/utils";

export type AgentNodeData = {
  persona: string;
  nodeType: WorkflowNodeType;
  telemetry: NodeTelemetry;
};

export type AgentFlowNode = Node<AgentNodeData, "agent">;

function AgentNodeComponent({ data }: NodeProps<AgentFlowNode>) {
  const { persona, nodeType, telemetry } = data;
  const style = STATE_STYLE[telemetry.status];
  const ringRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const previousStatus = useRef(telemetry.status);

  // Pulse ring while the node is generating. Looping tweens get the full
  // cleanup treatment: visibility pause, kill on unmount, reduced-motion skip.
  useEffect(() => {
    const element = ringRef.current;
    if (!element || telemetry.status !== "RUNNING") return;
    if (prefersReducedMotion()) {
      gsap.set(element, { opacity: 0.35, scale: 1.05 });
      return;
    }

    const tween = gsap.fromTo(
      element,
      { opacity: 0.55, scale: 0.97 },
      { opacity: 0, scale: 1.3, duration: 1.1, ease: "sine.out", repeat: -1 },
    );
    const onVisibility = () => (document.hidden ? tween.pause() : tween.resume());
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      tween.kill();
    };
  }, [telemetry.status]);

  // Emerald flash the instant the vector cache intercepts a prompt.
  useEffect(() => {
    const element = cardRef.current;
    const wasNotCached = previousStatus.current !== "CACHED";
    previousStatus.current = telemetry.status;

    if (!element || telemetry.status !== "CACHED" || !wasNotCached) return;
    if (prefersReducedMotion()) return;

    const tween = gsap.fromTo(
      element,
      { boxShadow: "0 0 0 0 hsl(160 84% 39% / 0.9)", scale: 1 },
      {
        boxShadow: "0 0 34px 6px hsl(160 84% 39% / 0)",
        scale: 1.04,
        duration: 0.55,
        ease: "power2.out",
        yoyo: true,
        repeat: 1,
      },
    );
    return () => {
      tween.kill();
    };
  }, [telemetry.status]);

  const Icon = nodeType === "llm_agent" ? Bot : Wrench;

  return (
    <div className="relative">
      {telemetry.status === "RUNNING" && (
        <div
          ref={ringRef}
          aria-hidden
          className="pointer-events-none absolute -inset-1 rounded-xl border-2 border-state-running"
        />
      )}

      <Handle type="target" position={Position.Top} className="!h-1.5 !w-1.5 !border-0 !bg-state-idle" />

      <div
        ref={cardRef}
        className={cn(
          "w-[204px] rounded-xl border bg-card px-3 py-2.5 transition-colors duration-200",
          style.border,
          style.glow,
        )}
      >
        <div className="flex items-center gap-2">
          <Icon className={cn("h-3.5 w-3.5 shrink-0", style.text)} />
          <span className="truncate text-[11px] font-medium leading-tight text-foreground">
            {persona}
          </span>
          {telemetry.is_cache_hit && (
            <Zap className="ml-auto h-3 w-3 shrink-0 text-state-cached" />
          )}
        </div>

        <div className={cn("mt-1.5 text-[10px] font-semibold uppercase tracking-wider", style.text)}>
          {style.label}
          {telemetry.is_cache_hit && " · <5ms instant hit"}
        </div>

        <div className="mt-2 grid grid-cols-3 gap-1 border-t border-border/60 pt-1.5 text-[10px] tabular">
          <Metric label="ms" value={telemetry.latency_ms.toLocaleString()} />
          <Metric label="tok" value={telemetry.tokens_consumed.toLocaleString()} />
          <Metric label="usd" value={telemetry.cost_usd.toFixed(5)} />
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-1.5 !w-1.5 !border-0 !bg-state-idle"
      />
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="leading-tight">
      <div className="text-foreground">{value}</div>
      <div className="text-[9px] uppercase text-muted-foreground">{label}</div>
    </div>
  );
}

export const AgentNode = memo(AgentNodeComponent);
