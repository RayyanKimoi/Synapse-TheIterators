# SYNAPSE Frontend — Phase 2

Dual-canvas execution arena bound to the backend's SSE telemetry stream.
Implements PRD Phase 2 (Frontend Scaffolding & Arena Architecture).

## Setup

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

The backend must be running first:

```bash
cd backend && uvicorn app.main:app --reload --port 8000
```

Point the UI elsewhere with `NEXT_PUBLIC_API_BASE` (defaults to
`http://localhost:8000`).

## Stack

Next.js 14 (App Router) · React 18 · TypeScript · Tailwind CSS · shadcn/ui ·
`@xyflow/react` 12 · GSAP 3 · Zustand 5 · lucide-react.

## Layout

```
app/
  layout.tsx            dark-only shell
  page.tsx              dashboard composition + backend discovery
  globals.css           SYNAPSE design tokens
components/
  TopNav.tsx            workflow selector, health badge, run triggers
  AgentRoster.tsx       left viewport
  AgentProfileCard.tsx  profile card + flight-status telemetry ribbon
  RaceArena.tsx         dual-canvas split screen with per-lane stopwatch
  FlowCanvas.tsx        one React Flow canvas (tiered or sequential layout)
  AgentNode.tsx         custom node: state borders, pulse ring, cache flash
  Scoreboard.tsx        footer counters and Trust & Safety badges
  ui/                   shadcn primitives
hooks/
  useWorkflowExecution.ts  SSE -> Zustand binding
  useCountUp.ts            GSAP counter interpolation
store/useTelemetryStore.ts per-pipeline run state
lib/
  api.ts, types.ts, layout.ts, node-state.ts, utils.ts
```

## Design tokens

Defined as HSL triplets on `:root` in `app/globals.css` so Tailwind's
`/opacity` modifiers keep working inside the shadcn primitives.

| Token | Value | Use |
| :--- | :--- | :--- |
| `--background` | `#08090C` | deep slate page |
| `--card` | `#12141A` | card surfaces |
| `--border` | `#27272A` | zinc borders |
| `--state-idle` | `#3F3F46` | IDLE node + edge |
| `--state-running` | `#06B6D4` | RUNNING cyan glow |
| `--state-cached` | `#10B981` | CACHED emerald flash |
| `--state-completed` | `#8B5CF6` | COMPLETED violet |
| `--state-failed` | `#EF4444` | FAILED crimson |

## Telemetry binding

`useWorkflowExecution(workflowId)` opens a native `EventSource` against the
backend's `GET /api/v1/execute/stream`, parses `telemetry_update` and
`run_complete`, and writes frames into the Zustand store. Each frame carries its
own `pipeline_type`, so one handler feeds both sides of the race.

EventSource reconnects automatically on a closed stream, which would re-run the
whole workflow, so every terminal path closes the connection explicitly.

GSAP counters write directly to the DOM node rather than through React state,
so a 100 ms frame never costs a re-render per tick. Every tween is killed on
cleanup, looping tweens pause on `visibilitychange`, and
`prefers-reduced-motion` jumps straight to the final value.

## Measured end to end

Against `workflows/deep_research.json`, verified in a headless browser:

| Run | Clock | Tokens | Spend | Cost avoided |
| :--- | ---: | ---: | ---: | ---: |
| Baseline | 35.0s | 994 | $0.00199 | — |
| Compiled | 8.80s | 751 | $0.00150 | $0.00049 |
| Compiled, warm cache | 0.36s | 296 | $0.00059 | $0.00140 |

## Phase 2 boundaries

Deferred by design: the Optimization Matchmaker swipe deck, the Anatomy
isometric explainer modal, and the Componentry `closing-plasma` /
`annotated-text` accents are all Phase 5. `liquid-chrome` and `pixel-canvas` are
in as CSS utilities. The compiler already returns
`plan.optimization_candidates`, so the swipe deck has its data source waiting.
