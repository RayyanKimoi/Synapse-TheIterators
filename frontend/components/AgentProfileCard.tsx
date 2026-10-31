"use client";

import { useState } from "react";
import { Bot, ChevronDown, Wrench, Zap } from "lucide-react";

import { formatMs, formatUsd, useCountUp } from "@/hooks/useCountUp";
import { STATE_STYLE } from "@/lib/node-state";
import type { NodeTelemetry, WorkflowNode } from "@/lib/types";
import { cn } from "@/lib/utils";

type AgentProfileCardProps = {
  node: WorkflowNode;
  telemetry: NodeTelemetry;
  depth: number | undefined;
};

/** Profile card for one agent, after Componentry's flight-status-card pattern:
 *  identity on top, a live telemetry ribbon underneath. */
export function AgentProfileCard({ node, telemetry, depth }: AgentProfileCardProps) {
  const [open, setOpen] = useState(false);
  const style = STATE_STYLE[telemetry.status];
  const Icon = node.type === "llm_agent" ? Bot : Wrench;

  const latencyRef = useCountUp(telemetry.latency_ms, formatMs, 0.2);
  const costRef = useCountUp(telemetry.cost_usd, formatUsd, 0.3);

  const running = telemetry.status === "RUNNING";

  return (
    <article
      className={cn(
        "group relative overflow-hidden rounded-2xl border bg-card/80 backdrop-blur-sm transition-all duration-200",
        style.border,
        style.glow,
      )}
    >
      {style.tint && <div aria-hidden className={cn("absolute inset-0", style.tint)} />}

      <div className="relative flex items-start gap-3 p-3">
        {/* Gradient avatar ring — the "profile" cue. */}
        <div className="relative shrink-0">
          <div
            className={cn(
              "flex h-11 w-11 items-center justify-center rounded-full bg-gradient-to-br p-[1.5px]",
              node.type === "llm_agent"
                ? "from-state-running/80 via-state-completed/70 to-state-cached/60"
                : "from-state-completed/70 via-white/20 to-state-running/50",
            )}
          >
            <span
              className={cn(
                "flex h-full w-full items-center justify-center rounded-full bg-card",
                style.text,
              )}
            >
              <Icon className="h-4 w-4" />
            </span>
          </div>
          <span
            className={cn(
              "absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-card",
              style.dot,
              running && "animate-pulse motion-reduce:animate-none",
            )}
          />
        </div>

        <div className="min-w-0 flex-1">
          <h3 className="truncate text-[13px] font-semibold leading-tight text-foreground">
            {node.persona}
          </h3>
          <p className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground">
            {node.type === "llm_agent" ? node.model : node.tool_name}
          </p>
          <div className="mt-1.5 flex items-center gap-1">
            <span
              className={cn(
                "rounded-full border px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider",
                style.border,
                style.text,
              )}
            >
              {style.label}
            </span>
            {depth !== undefined && (
              <span className="rounded-full border border-white/[0.08] px-1.5 py-px text-[9px] uppercase tracking-wider text-muted-foreground">
                depth {depth}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Live telemetry ribbon. */}
      <div className="relative grid grid-cols-3 gap-px border-t border-white/[0.07] bg-white/[0.05] text-center">
        <Ribbon label="Latency" unit="ms">
          <span ref={latencyRef}>0</span>
        </Ribbon>
        <Ribbon label="Cost">
          <span ref={costRef}>$0.00000</span>
        </Ribbon>
        <Ribbon label="Cache">
          {telemetry.is_cache_hit ? (
            <span className="inline-flex items-center gap-0.5 text-state-cached">
              <Zap className="h-2.5 w-2.5 fill-current" />
              HIT
            </span>
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </Ribbon>
      </div>

      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="relative flex w-full items-center justify-center gap-1 border-t border-white/[0.07] py-1.5 text-[10px] text-muted-foreground transition-colors hover:bg-white/[0.04] hover:text-foreground"
      >
        Agent bio
        <ChevronDown className={cn("h-3 w-3 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <p className="relative border-t border-white/[0.07] px-3 py-2 text-[10px] leading-relaxed text-muted-foreground">
          {node.system_prompt}
        </p>
      )}
    </article>
  );
}

function Ribbon({
  label,
  unit,
  children,
}: {
  label: string;
  unit?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-card px-1 py-1.5">
      <div className="tabular text-[11px] font-semibold text-foreground">
        {children}
        {unit && <span className="ml-0.5 text-[9px] font-normal text-muted-foreground">{unit}</span>}
      </div>
      <div className="text-[9px] uppercase tracking-wide text-muted-foreground/80">{label}</div>
    </div>
  );
}
