/**
 * Budget burn: how much of a run's budget each pipeline has spent, and when to
 * say so. Pure functions only, so the alert rules can be checked in isolation.
 */

/** Warn here. */
export const WARN_PCT = 80;
/** The breaker's line. It can also trip *below* this: the gateway refuses the
 *  call whose worst-case cost would cross the budget, so spend stops short. */
export const BREAKER_PCT = 100;

export type BudgetLevel = "warn" | "breaker";

export type BudgetSample = {
  /** Elapsed pipeline time, ms. */
  t: number;
  costUsd: number;
  tokens: number;
};

const MAX_SAMPLES = 600;

export function usagePct(costUsd: number, budgetUsd: number): number {
  return budgetUsd > 0 ? (costUsd / budgetUsd) * 100 : 0;
}

/**
 * Levels to announce now, given what this run has already announced. The
 * breaker is driven by the breaker's own status, not only by the percentage,
 * and a run that jumps straight past both lines gets one alert, not two.
 */
export function levelsToAnnounce(
  pct: number,
  tripped: boolean,
  announced: ReadonlySet<BudgetLevel>,
): BudgetLevel[] {
  if (announced.has("breaker")) return [];
  if (tripped || pct >= BREAKER_PCT) return ["breaker"];
  if (pct >= WARN_PCT && !announced.has("warn")) return ["warn"];
  return [];
}

/**
 * Top of the chart's y axis, in percent. A run that barely touches its budget
 * still gets a readable line; once spend nears the alert line, the axis
 * extends past 100% so both threshold lines are on screen.
 */
export function budgetCeiling(peakPct: number): number {
  if (peakPct >= 60) return Math.max(110, Math.ceil(peakPct * 1.05));
  const target = Math.max(peakPct * 1.25, 0.5);
  return [0.5, 1, 2, 5, 10, 20, 50, 80].find((step) => step >= target) ?? 110;
}

/** Appends a frame's spend, skipping repeats and keeping the history bounded. */
export function appendSample(samples: BudgetSample[], sample: BudgetSample): BudgetSample[] {
  const last = samples[samples.length - 1];
  if (last && last.t === sample.t && last.costUsd === sample.costUsd) return samples;
  const next = [...samples, sample];
  return next.length > MAX_SAMPLES ? next.slice(next.length - MAX_SAMPLES) : next;
}

/** "$0.50" for real budgets, "$0.0030" for the tight ones used to rehearse alerts. */
export function formatBudget(usd: number): string {
  return `$${usd >= 0.1 ? usd.toFixed(2) : usd.toFixed(4)}`;
}

export function formatPctTight(pct: number): string {
  if (pct === 0) return "0%";
  if (pct < 1) return `${pct.toFixed(2)}%`;
  if (pct < 10) return `${pct.toFixed(1)}%`;
  return `${Math.round(pct)}%`;
}
