/**
 * Sample data for the dashboard views that have no backend behind them yet.
 *
 * Usage history, the model registry, API keys and billing are UI shells: there
 * are no endpoints for them, and this build was scoped to the frontend. Every
 * invented value lives in this one file so it is obvious what is real and what
 * is staged — swapping any of these for a fetch is a one-line change at the
 * call site.
 *
 * Figures that ARE real (the measured runs) are marked as such.
 */

export type LedgerStatus = "success" | "waiting" | "failed";

export type LedgerEntry = {
  id: string;
  title: string;
  pipeline: "compiled" | "baseline" | "race";
  status: LedgerStatus;
  /** Relative, so the ledger never looks stale in a demo. */
  when: string;
  latencyMs: number;
  tokens: number;
  costUsd: number;
  tags: string[];
};

/** Latencies here mirror the measured runs recorded in CLAUDE_UPDATE.md. */
export const LEDGER: LedgerEntry[] = [
  {
    id: "run_8f21",
    title: "Deep research — NVIDIA Q3 exposure",
    pipeline: "compiled",
    status: "success",
    when: "2 minutes ago",
    latencyMs: 10717,
    tokens: 3184,
    costUsd: 0.0061,
    tags: ["deep-research", "fused", "warm-paste"],
  },
  {
    id: "run_8f20",
    title: "Deep research — NVIDIA Q3 exposure",
    pipeline: "baseline",
    status: "success",
    when: "3 minutes ago",
    latencyMs: 31052,
    tokens: 5454,
    costUsd: 0.0109,
    tags: ["deep-research", "serial"],
  },
  {
    id: "run_8f1d",
    title: "Arena race — cold transition matrix",
    pipeline: "race",
    status: "success",
    when: "18 minutes ago",
    latencyMs: 15266,
    tokens: 4902,
    costUsd: 0.0094,
    tags: ["race", "cold-paste"],
  },
  {
    id: "run_8f19",
    title: "Supply-chain sentiment sweep",
    pipeline: "compiled",
    status: "waiting",
    when: "26 minutes ago",
    latencyMs: 0,
    tokens: 0,
    costUsd: 0,
    tags: ["queued", "tool-io"],
  },
  {
    id: "run_8f12",
    title: "Deep research — Tesla margin outlook",
    pipeline: "compiled",
    status: "failed",
    when: "1 hour ago",
    latencyMs: 4120,
    tokens: 812,
    costUsd: 0.0017,
    tags: ["circuit-breaker", "budget"],
  },
  {
    id: "run_8f0b",
    title: "Cache warm — reference workflow",
    pipeline: "compiled",
    status: "success",
    when: "2 hours ago",
    latencyMs: 5075,
    tokens: 0,
    costUsd: 0,
    tags: ["cache-warm", "redis"],
  },
];

export const LEDGER_TAGS = Array.from(new Set(LEDGER.flatMap((entry) => entry.tags))).sort();

export type ModelEntry = {
  id: string;
  name: string;
  vendor: string;
  params: string;
  context: string;
  /** Per million tokens, USD. */
  inputPrice: number;
  outputPrice: number;
  status: "available" | "tunnel" | "unconfigured";
  note: string;
};

export const MODELS: ModelEntry[] = [
  {
    id: "openai/qwen2.5-3b-instruct",
    name: "Qwen 2.5 3B Instruct",
    vendor: "Qwen",
    params: "3B",
    context: "32K",
    inputPrice: 0.0,
    outputPrice: 0.0,
    status: "tunnel",
    note: "Self-hosted over the litellm proxy. The reference workflow declares this model.",
  },
  {
    id: "meta/llama-3.1-8b-instruct",
    name: "Llama 3.1 8B Instruct",
    vendor: "Meta",
    params: "8B",
    context: "128K",
    inputPrice: 0.18,
    outputPrice: 0.18,
    status: "available",
    note: "Larger context for long upstream payloads; fusion still requires one model per chain.",
  },
  {
    id: "mistral/mistral-small-latest",
    name: "Mistral Small",
    vendor: "Mistral",
    params: "22B",
    context: "128K",
    inputPrice: 0.2,
    outputPrice: 0.6,
    status: "available",
    note: "Stronger reasoning for the synthesis tail at a higher per-token cost.",
  },
  {
    id: "google/gemini-3.5-flash",
    name: "Gemini 3.5 Flash",
    vendor: "Google",
    params: "—",
    context: "1M",
    inputPrice: 0.075,
    outputPrice: 0.3,
    status: "unconfigured",
    note: "Used by the LLM-as-a-judge. Needs a key on the API keys tab before it can run.",
  },
];

export type PlanTier = {
  id: string;
  name: string;
  price: string;
  cadence: string;
  blurb: string;
  features: string[];
  current: boolean;
};

export const TIERS: PlanTier[] = [
  {
    id: "dev",
    name: "Developer",
    price: "$0",
    cadence: "forever",
    blurb: "One workspace, local runtime, full compiler.",
    features: ["10K gateway requests / mo", "Semantic cache (in-memory)", "Community support"],
    current: false,
  },
  {
    id: "team",
    name: "Team",
    price: "$180",
    cadence: "per month",
    blurb: "Shared workspaces and a managed cache.",
    features: [
      "500K gateway requests / mo",
      "Redis-backed semantic cache",
      "Langfuse trace retention, 30 days",
      "LLM-as-a-judge evaluations",
    ],
    current: true,
  },
  {
    id: "scale",
    name: "Scale",
    price: "Custom",
    cadence: "annual",
    blurb: "Dedicated capacity with an SLA on the critical path.",
    features: [
      "Unlimited gateway requests",
      "Private model routing (BYOK)",
      "Trace retention, 1 year",
      "Priority support, 99.9% SLA",
    ],
    current: false,
  },
];

export type UsageMeter = {
  label: string;
  used: number;
  limit: number;
  unit: string;
};

export const USAGE: UsageMeter[] = [
  { label: "Gateway requests", used: 405_200, limit: 500_000, unit: "" },
  { label: "Cache storage", used: 1.9, limit: 5, unit: " GB" },
  { label: "Trace retention", used: 12, limit: 30, unit: " days" },
];
