"use client";

import { memo, useEffect, useRef } from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import gsap from "gsap";
import { Bot, Check, Loader2, Wrench, Zap } from "lucide-react";

import { prefersReducedMotion } from "@/hooks/useCountUp";
import { STATE_STYLE } from "@/lib/node-state";
import type { NodeTelemetry, WorkflowNodeType } from "@/lib/types";
import { cn } from "@/lib/utils";

export type AgentNodeData = {
  persona: string;
  nodeType: WorkflowNodeType;
  telemetry: NodeTelemetry;
  variant: "baseline" | "compiled";
  /** False until execution reaches this node; drives the fade-in. */
  revealed: boolean;
};

export type AgentFlowNode = Node<AgentNodeData, "agent">;

function AgentNodeComponent({ data }: NodeProps<AgentFlowNode>) {
  const { persona, nodeType, telemetry, variant, revealed } = data;
  const style = STATE_STYLE[telemetry.status];
  const ringRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const previousStatus = useRef(telemetry.status);

  const running = telemetry.status === "RUNNING";
  const cached = telemetry.status === "CACHED";
  const blocking = running && variant === "baseline";

  // Pulse ring while the node is generating. Looping tweens get the full
  // cleanup treatment: visibility pause, kill on unmount, reduced-motion skip.
  useEffect(() => {
    const element = ringRef.current;
    if (!element || !running) return;
    if (prefersReducedMotion()) {
      gsap.set(element, { opacity: 0.35, scale: 1.05 });
      return;
    }

    const tween = gsap.fromTo(
      element,
      { opacity: 0.6, scale: 0.97 },
      { opacity: 0, scale: 1.32, duration: 1.15, ease: "sine.out", repeat: -1 },
    );
    const onVisibility = () => (document.hidden ? tween.pause() : tween.resume());
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      tween.kill();
    };
  }, [running]);

  // Emerald flash the instant the vector cache intercepts a prompt.
  useEffect(() => {
    const element = cardRef.current;
    const wasNotCached = previousStatus.current !== "CACHED";
    previousStatus.current = telemetry.status;

    if (!element || !cached || !wasNotCached) return;
    if (prefersReducedMotion()) return;

    const tween = gsap.fromTo(
      element,
      { boxShadow: "0 0 0 0 hsl(160 84% 39% / 0.95)", scale: 1 },
      {
        boxShadow: "0 0 46px 10px hsl(160 84% 39% / 0)",
        scale: 1.055,
        duration: 0.5,
        ease: "power3.out",
        yoyo: true,
        repeat: 1,
      },
    );
    return () => {
      tween.kill();
    };
  }, [cached, telemetry.status]);

  const Icon = nodeType === "llm_agent" ? Bot : Wrench;

  return (
    <div
      className="relative transition-[opacity,transform] duration-[550ms] ease-out motion-reduce:transition-none"
      style={{
        opacity: revealed ? 1 : 0,
        transform: revealed ? "none" : "translateY(10px)",
        pointerEvents: revealed ? undefined : "none",
      }}
    >
      {running && (
        <div
          ref={ringRef}
          aria-hidden
          className={cn(
            "pointer-events-none absolute -inset-1 rounded-2xl border-2",
            blocking ? "border-state-blocking" : "border-state-running",
          )}
        />
      )}

      <Handle
        type="target"
        position={Position.Top}
        className="!h-1.5 !w-1.5 !border-0 !bg-white/25"
      />

      <div
        ref={cardRef}
        className={cn(
          "relative w-[214px] overflow-hidden rounded-2xl border bg-card/90 backdrop-blur-sm transition-colors duration-200",
          blocking ? "border-state-blocking/80" : style.border,
          blocking
            ? "shadow-[0_0_30px_-8px_hsl(var(--state-blocking)/0.75)]"
            : style.glow,
        )}
      >
        {style.tint && <div aria-hidden className={cn("absolute inset-0", style.tint)} />}

        {/* Rigid blocking indicator: the baseline lane stalls, visibly. */}
        {blocking && <div aria-hidden className="blocking-bar h-[3px] w-full" />}

        <div className="relative px-3 py-2.5">
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "flex h-6 w-6 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04]",
                blocking ? "text-state-blocking" : style.text,
              )}
            >
              <Icon className="h-3.5 w-3.5" />
            </span>

            <span className="truncate text-[11px] font-medium leading-tight text-foreground">
              {persona}
            </span>

            {/* Cache hit replaces the spinner with a lightning badge. */}
            {cached ? (
              <span className="ml-auto flex shrink-0 items-center gap-0.5 rounded-full border border-state-cached/60 bg-state-cached/15 px-1.5 py-0.5 text-[9px] font-semibold text-state-cached">
                <Zap className="h-2.5 w-2.5 fill-current" />
                HIT
              </span>
            ) : running ? (
              <Loader2
                className={cn(
                  "ml-auto h-3 w-3 shrink-0 animate-spin motion-reduce:animate-none",
                  blocking ? "text-state-blocking" : "text-state-running",
                )}
              />
            ) : telemetry.status === "COMPLETED" ? (
              <Check className="ml-auto h-3 w-3 shrink-0 text-state-completed" />
            ) : null}
          </div>

          <div className="mt-1.5 flex items-center gap-1.5">
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                blocking ? "bg-state-blocking" : style.dot,
                running && "animate-pulse motion-reduce:animate-none",
              )}
            />
            <span
              className={cn(
                "text-[9.5px] font-semibold uppercase tracking-[0.14em]",
                blocking ? "text-state-blocking" : style.text,
              )}
            >
              {blocking ? "Blocking I/O" : style.label}
              {cached && " · <5ms"}
            </span>
          </div>

          <div className="mt-2 grid grid-cols-3 gap-1 border-t border-white/[0.07] pt-1.5 text-[10px] tabular">
            <Metric label="ms" value={telemetry.latency_ms.toLocaleString()} />
            <Metric label="tok" value={telemetry.tokens_consumed.toLocaleString()} />
            <Metric label="usd" value={telemetry.cost_usd.toFixed(5)} />
          </div>
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-1.5 !w-1.5 !border-0 !bg-white/25"
      />
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="leading-tight">
      <div className="text-foreground/90">{value}</div>
      <div className="text-[9px] uppercase tracking-wide text-muted-foreground/70">{label}</div>
    </div>
  );
}

export const AgentNode = memo(AgentNodeComponent);
