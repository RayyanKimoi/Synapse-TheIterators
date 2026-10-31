"use client";

import { useState } from "react";
import { Bot, ChevronDown, Wrench } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { formatMs, formatTokens, formatUsd, useCountUp } from "@/hooks/useCountUp";
import { STATE_STYLE } from "@/lib/node-state";
import type { NodeTelemetry, WorkflowNode } from "@/lib/types";
import { cn } from "@/lib/utils";

type AgentProfileCardProps = {
  node: WorkflowNode;
  telemetry: NodeTelemetry;
  depth: number | undefined;
};

export function AgentProfileCard({ node, telemetry, depth }: AgentProfileCardProps) {
  const [open, setOpen] = useState(false);
  const style = STATE_STYLE[telemetry.status];
  const Icon = node.type === "llm_agent" ? Bot : Wrench;

  const latencyRef = useCountUp(telemetry.latency_ms, formatMs, 0.2);
  const tokensRef = useCountUp(telemetry.tokens_consumed, formatTokens, 0.3);
  const costRef = useCountUp(telemetry.cost_usd, formatUsd, 0.3);

  return (
    <article
      className={cn(
        "rounded-xl border bg-card transition-colors duration-200",
        style.border,
        style.glow,
      )}
    >
      <div className="flex items-start gap-2.5 p-3">
        <div className={cn("mt-0.5 rounded-md border border-border/80 bg-background p-1.5", style.text)}>
          <Icon className="h-3.5 w-3.5" />
        </div>

        <div className="min-w-0 flex-1">
          <h3 className="line-clamp-2 text-xs font-medium leading-snug text-foreground">
            {node.persona}
          </h3>
          <p className="truncate text-[10px] text-muted-foreground">
            {node.type === "llm_agent" ? node.model : node.tool_name}
            {depth !== undefined && ` · tier ${depth}`}
          </p>
        </div>

        <Badge
          variant="outline"
          className={cn("shrink-0 text-[9px] uppercase tracking-wide", style.border, style.text)}
        >
          {style.label}
        </Badge>
      </div>

      {/* Telemetry ribbon, after Componentry's flight-status-card pattern. */}
      <div className="grid grid-cols-3 gap-px border-t border-border bg-border/50 text-center">
        <Ribbon label="Latency" unit="ms">
          <span ref={latencyRef}>0</span>
        </Ribbon>
        <Ribbon label="Tokens">
          <span ref={tokensRef}>0</span>
        </Ribbon>
        <Ribbon label="Cost">
          <span ref={costRef}>$0.00000</span>
        </Ribbon>
      </div>

      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center justify-center gap-1 rounded-b-xl border-t border-border py-1 text-[10px] text-muted-foreground transition-colors hover:bg-secondary/40 hover:text-foreground"
      >
        Agent bio
        <ChevronDown className={cn("h-3 w-3 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <p className="border-t border-border px-3 py-2 text-[10px] leading-relaxed text-muted-foreground">
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
      <div className="text-[9px] uppercase tracking-wide text-muted-foreground">{label}</div>
    </div>
  );
}
