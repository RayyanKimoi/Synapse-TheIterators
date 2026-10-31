"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import gsap from "gsap";
import {
  Check,
  ChevronDown,
  Coins,
  GitBranch,
  Layers,
  type LucideIcon,
  Sparkles,
  Timer,
  X,
  Zap,
} from "lucide-react";

import { prefersReducedMotion } from "@/hooks/useCountUp";
import type { OptimizationCandidate } from "@/lib/types";
import { cn } from "@/lib/utils";

const SWIPE_THRESHOLD = 104;

/** Keyed by every `kind` the compiler emits, so a new pass cannot fall through
 *  to another pass's icon the way a two-way ternary let it. */
const KIND_PRESENTATION: Record<
  OptimizationCandidate["kind"],
  { icon: LucideIcon; label: string }
> = {
  parallelize: { icon: GitBranch, label: "Ready-Node dispatch" },
  prompt_fusion: { icon: Layers, label: "DSPy prompt fusion" },
  speculative_prefetch: { icon: Zap, label: "PASTE speculative prefetch" },
};

type MatchmakerDeckProps = {
  candidates: OptimizationCandidate[];
  onApprove: (candidate: OptimizationCandidate) => void;
  busy: boolean;
};

/**
 * "Tinder for optimizations" (PRD 9.3). Swipe right to inject the compiler
 * pass into the DAG, left to keep procedural execution.
 *
 * Drag is hand-rolled on pointer events rather than a GSAP plugin so the deck
 * has no extra dependency, and every gesture has an equivalent button — a
 * drag-only control is unreachable by keyboard.
 */
export function MatchmakerDeck({ candidates, onApprove, busy }: MatchmakerDeckProps) {
  const [index, setIndex] = useState(0);
  const [verdict, setVerdict] = useState<"approve" | "reject" | null>(null);
  // null = follow the run state; true/false = the user overrode it.
  const [override, setOverride] = useState<boolean | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const drag = useRef({ active: false, startX: 0, dx: 0 });

  const current = candidates[index];
  const remaining = candidates.length - index;

  // The deck owns the stage before a run (PRD Act 2) and gets out of the
  // arena's way once nodes start firing (Act 3), where it would otherwise
  // cover the concurrent dispatch that is the whole point of the race.
  const open = override ?? !busy;

  // Starting a run collapses the deck and leaves it collapsed afterwards, so
  // the finale (emerald cache hits) is never covered. Reopening is explicit.
  useEffect(() => {
    if (busy) setOverride(false);
  }, [busy]);

  useEffect(() => {
    setIndex(0);
  }, [candidates]);

  // Reset the card transform whenever a new candidate takes the top slot.
  useEffect(() => {
    const element = cardRef.current;
    if (!element) return;
    gsap.set(element, { x: 0, rotate: 0, opacity: 1 });
    setVerdict(null);
  }, [index]);

  const settle = useCallback(
    (direction: "approve" | "reject") => {
      const element = cardRef.current;
      const candidate = candidates[index];
      if (!candidate) return;

      const commit = () => {
        if (direction === "approve") onApprove(candidate);
        setIndex((value) => value + 1);
      };

      if (!element || prefersReducedMotion()) {
        commit();
        return;
      }

      gsap.to(element, {
        x: direction === "approve" ? 420 : -420,
        rotate: direction === "approve" ? 14 : -14,
        opacity: 0,
        duration: 0.34,
        ease: "power3.in",
        onComplete: commit,
      });
    },
    [candidates, index, onApprove],
  );

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (busy || !current) return;
    drag.current = { active: true, startX: event.clientX, dx: 0 };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!drag.current.active) return;
    const element = cardRef.current;
    if (!element) return;

    const dx = event.clientX - drag.current.startX;
    drag.current.dx = dx;
    gsap.set(element, { x: dx, rotate: dx * 0.045 });
    setVerdict(dx > 48 ? "approve" : dx < -48 ? "reject" : null);
  };

  const onPointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!drag.current.active) return;
    drag.current.active = false;
    event.currentTarget.releasePointerCapture(event.pointerId);

    const { dx } = drag.current;
    if (dx > SWIPE_THRESHOLD) return settle("approve");
    if (dx < -SWIPE_THRESHOLD) return settle("reject");

    setVerdict(null);
    const element = cardRef.current;
    if (element) {
      gsap.to(element, { x: 0, rotate: 0, duration: 0.42, ease: "elastic.out(1, 0.62)" });
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOverride(true)}
        className="pointer-events-auto flex min-h-[44px] items-center gap-2 rounded-2xl border border-white/[0.09] liquid-chrome px-3.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground transition-colors hover:text-foreground"
      >
        <Sparkles className="h-3.5 w-3.5 text-state-completed" />
        Matchmaker
        <span
          className={cn(
            "tabular rounded-full px-1.5 py-0.5 text-[10px]",
            remaining > 0
              ? "bg-state-completed/20 text-state-completed"
              : "bg-state-cached/20 text-state-cached",
          )}
        >
          {remaining > 0 ? remaining : "✓"}
        </span>
      </button>
    );
  }

  if (!current) {
    return (
      <div className="pointer-events-auto w-[320px] rounded-2xl border border-white/[0.08] liquid-chrome p-4 text-center">
        <Sparkles className="mx-auto h-4 w-4 text-state-cached" />
        <p className="mt-2 text-xs font-semibold text-foreground">Graph fully compiled</p>
        <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
          Every detected pass has been reviewed. Run the arena race to see the
          compiled dispatch against the baseline.
        </p>
      </div>
    );
  }

  const { icon: Icon, label: kindLabel } = KIND_PRESENTATION[current.kind];

  return (
    <div className="pointer-events-auto w-[320px]">
      <div className="mb-2 flex items-center justify-between px-1">
        <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
          <Sparkles className="h-3 w-3 text-state-completed" />
          Optimization Matchmaker
        </span>
        <span className="flex items-center gap-1.5">
          <span className="tabular text-[10px] text-muted-foreground">
            {remaining} pending
          </span>
          <button
            type="button"
            onClick={() => setOverride(false)}
            aria-label="Collapse the matchmaker deck"
            className="flex h-6 w-6 items-center justify-center rounded-lg border border-white/[0.09] text-muted-foreground transition-colors hover:text-foreground"
          >
            <ChevronDown className="h-3.5 w-3.5" />
          </button>
        </span>
      </div>

      <div className="relative">
        {/* Peeked cards behind the top one, so the deck reads as a stack. */}
        {remaining > 2 && (
          <div className="absolute inset-x-4 -bottom-2 h-full rounded-2xl border border-white/[0.05] bg-card/30" />
        )}
        {remaining > 1 && (
          <div className="absolute inset-x-2 -bottom-1 h-full rounded-2xl border border-white/[0.06] bg-card/45" />
        )}

        <div
          ref={cardRef}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          className={cn(
            "relative cursor-grab touch-none select-none overflow-hidden rounded-2xl border bg-card/95 backdrop-blur-md active:cursor-grabbing",
            verdict === "approve"
              ? "border-state-cached/70 shadow-[0_0_38px_-10px_hsl(var(--state-cached)/0.9)]"
              : verdict === "reject"
                ? "border-state-failed/70 shadow-[0_0_38px_-10px_hsl(var(--state-failed)/0.9)]"
                : "border-white/[0.09] shadow-[0_24px_50px_-28px_hsl(225_60%_2%/0.95)]",
          )}
        >
          <div
            aria-hidden
            className={cn(
              "pointer-events-none absolute inset-0 transition-opacity duration-150",
              verdict === "approve"
                ? "bg-state-cached/10 opacity-100"
                : verdict === "reject"
                  ? "bg-state-failed/10 opacity-100"
                  : "opacity-0",
            )}
          />

          <div className="relative p-4">
            <div className="flex items-start gap-2.5">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-state-completed/40 bg-state-completed/10 text-state-completed">
                <Icon className="h-4 w-4" />
              </span>
              <div className="min-w-0 flex-1">
                <h3 className="text-[13px] font-semibold leading-snug text-foreground">
                  {current.title}
                </h3>
                <span className="mt-0.5 inline-block rounded-full border border-white/10 px-1.5 py-px text-[9px] uppercase tracking-wider text-muted-foreground">
                  {kindLabel}
                </span>
              </div>
            </div>

            <p className="mt-2.5 text-[11px] leading-relaxed text-muted-foreground">
              {current.rationale}
            </p>

            <div className="mt-3 grid grid-cols-3 gap-px overflow-hidden rounded-xl border border-white/[0.07] bg-white/[0.05] text-center">
              <Projection
                icon={<Timer className="h-3 w-3" />}
                label="Latency"
                value={`−${(current.projected_latency_saved_ms / 1000).toFixed(1)}s`}
                tone="text-state-running"
              />
              <Projection
                icon={<Coins className="h-3 w-3" />}
                label="Tokens"
                value={`−${current.projected_tokens_saved.toLocaleString()}`}
                tone="text-state-completed"
              />
              <Projection
                icon={<Coins className="h-3 w-3" />}
                label="Cost"
                value={`−$${current.projected_cost_saved_usd.toFixed(5)}`}
                tone="text-state-cached"
              />
            </div>

            <div className="mt-3 flex flex-wrap gap-1">
              {current.node_ids.map((id) => (
                <span
                  key={id}
                  className="rounded-md border border-white/[0.07] bg-background/60 px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground"
                >
                  {id}
                </span>
              ))}
            </div>
          </div>

          <div className="relative grid grid-cols-2 gap-2 border-t border-white/[0.07] p-3">
            <button
              type="button"
              onClick={() => settle("reject")}
              disabled={busy}
              className="flex min-h-[44px] items-center justify-center gap-1.5 rounded-xl border border-white/[0.09] text-[11px] font-semibold uppercase tracking-wider text-muted-foreground transition-colors hover:border-state-failed/60 hover:text-state-failed disabled:opacity-40"
            >
              <X className="h-3.5 w-3.5" />
              Reject
            </button>
            <button
              type="button"
              onClick={() => settle("approve")}
              disabled={busy}
              className="flex min-h-[44px] items-center justify-center gap-1.5 rounded-xl border border-state-cached/50 bg-state-cached/15 text-[11px] font-semibold uppercase tracking-wider text-state-cached transition-colors hover:bg-state-cached/25 disabled:opacity-40"
            >
              <Check className="h-3.5 w-3.5" />
              Approve
            </button>
          </div>
        </div>
      </div>

      <p className="mt-2 text-center text-[10px] text-muted-foreground/80">
        Drag the card, or use the buttons
      </p>
    </div>
  );
}

function Projection({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone: string;
}) {
  return (
    <div className="bg-card px-1 py-2">
      <div className="flex items-center justify-center gap-0.5 text-[9px] uppercase tracking-wider text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className={cn("tabular mt-0.5 text-[12px] font-semibold", tone)}>{value}</div>
    </div>
  );
}
