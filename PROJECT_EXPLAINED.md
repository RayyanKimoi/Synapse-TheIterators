# SYNAPSE — Project Explained (Plain English)

---

## What Is This Project?

**SYNAPSE** is a platform that runs AI agent workflows — and makes them faster and cheaper.

Imagine you have a task like "research NVIDIA stock and write a report." Instead of doing it step by step (search → analyze → draft → summarize), SYNAPSE figures out which steps can run **at the same time**, which answers can be **reused from a cache**, and which LLM calls can be **merged into one**. It then shows you a live side-by-side race: the slow naive way vs the smart optimized way.

---

## The Two Sides

```
Website (Next.js)           Server (Python / FastAPI)
─────────────────           ─────────────────────────
/ Landing page              Compiles workflows
/dashboard Arena            Runs agents
/dashboard/history etc.     Streams live updates → browser
```

The browser and server talk over **SSE (Server-Sent Events)** — basically a one-way live feed where the server pushes JSON updates to the browser every 100ms as nodes execute.

---

## Key Concepts (Simple Definitions)

| Term | What it means |
|------|--------------|
| **Workflow** | A JSON file describing a set of AI tasks and how they depend on each other |
| **Node** | One task — either an LLM call (AI thinking) or a Tool call (e.g. web search) |
| **DAG** | Directed Acyclic Graph — a map of which task depends on which, with no circular loops |
| **Compile** | Analysing the workflow before running it to find optimizations |
| **Baseline** | Running tasks one after another (serial/slow, the naive way) |
| **Compiled** | Running tasks in parallel with all optimizations applied (the smart way) |
| **SSE** | Live data feed from server to browser — like a radio signal that never stops |
| **Circuit Breaker** | A cost limit — if spending is about to go over budget, it cuts off all downstream tasks |
| **Semantic Cache** | A smart cache — if you ask "What is NVIDIA's revenue?" and the cache has "What are NVIDIA's earnings?", it recognizes they're the same question and returns the stored answer |

---

## How a Workflow is Defined

Every workflow is a JSON file (stored in `workflows/`). Here's what it contains:

```
workflow_id: "deep_research"
nodes:
  - id: "node_search_filings"
    type: tool_io              ← calls Tavily web search
    dependencies: []           ← runs first, no deps
    
  - id: "node_analyze"
    type: llm_agent            ← calls an LLM
    model: "qwen2.5-3b"
    dependencies: ["node_search_filings"]  ← waits for search to finish

  ...

budget_limit_usd: 0.50         ← hard cost ceiling
test_assertions:
  required_output_keys: ["summary", "risk_factors"]
  max_acceptable_latency_ms: 15000
```

The workflow is validated at compile time — if there's a circular dependency (A depends on B, B depends on A), it's **rejected immediately** before a single token is spent.

---

## Step-by-Step: What Happens When You Click "Race"

### Step 1 — Page Load
When you open `/dashboard`, the browser:
1. Calls `GET /api/v1/workflows` → gets the list of available workflows
2. Calls `GET /api/v1/health` → checks if the backend + LLM are reachable
3. Calls `POST /api/v1/compile` with the selected workflow → gets back the optimization plan

### Step 2 — Compilation (the smart part)
The compiler analyses the workflow DAG and finds:

**Parallelism opportunities** — nodes with no dependency on each other can run at the same time instead of waiting. The "Ready-Node scheduler" tracks how many dependencies each node still has (`in_degree`). The moment a node's count hits zero, it dispatches immediately.

**Prompt Fusion** — if two LLM nodes are on the same model, feed into each other, and have no side effects, they get merged into a single LLM call using DSPy. Instead of: "Call LLM → wait → call LLM again", it becomes: "Call LLM once, get both answers".

**Speculative Pre-fetching (PASTE)** — SYNAPSE watches which tool calls historically follow which LLM calls (stored in a SQLite database). If "tool_search" follows "node_analyze" 80% of the time, SYNAPSE fires the search request *before* the LLM even finishes, so the round trip overlaps the generation time.

**Semantic Cache** — before calling an LLM, SYNAPSE embeds the query into a 384-dimensional vector and checks Redis. If a past answer is close enough (cosine similarity ≥ 0.88), it returns that answer instantly. Two vectors are used — the user query AND the upstream context — to avoid false matches.

All of this is returned to the frontend as a `CompilePlan` with projected latency savings.

### Step 3 — The Race Starts
Clicking **Race** fires two parallel SSE streams at the same time:
- `?mode=baseline` → runs the workflow as a serial chain (one task at a time)
- `?mode=compiled` → runs the workflow with all optimizations

Both streams send a `TelemetryFrame` every 100ms. Each frame contains the current status of every node.

### Step 4 — Live Updates in the Browser
The React Flow canvas (the graph view) reads from a **Zustand store** that's fed by the SSE stream. As frames arrive:
- Nodes change color: grey (idle) → cyan (running) → emerald (cached) → violet (completed) → red (failed)
- GSAP stopwatches on each node tick up in real time
- Animated particles flow along the edges — slow on baseline, fast on compiled, bright green burst on a cache hit

### Step 5 — Run Finishes
When all nodes complete, the server sends a final `RunSummary` with:
- Total elapsed time
- Tokens used and cost
- Contract verdict (did the output have all required keys? Was it fast enough?)

The **Scoreboard** appears showing baseline vs compiled side by side.

---

## The Four Optimizations (Simple Explanation)

### 1. Parallelism
**Problem:** Tasks that don't depend on each other are still running one at a time.
**Fix:** Run them simultaneously. If searching SEC filings and searching news have no shared dependency, fire both at once.
**Visual:** Two arrows on the canvas departing from the same node at the same time.

### 2. Prompt Fusion
**Problem:** Two LLM calls that could be one call. Example: "Draft findings" → "Synthesize report" — both feed into each other, same model, no side effects.
**Fix:** Merge them into one LLM call using DSPy. One request, two outputs.
**Saving:** Eliminates one full LLM round trip.

### 3. Semantic Cache
**Problem:** The same (or very similar) question is asked in multiple runs. Each time pays full LLM cost.
**Fix:** Embed the question as a vector. If a past answer is a close enough match (above the similarity threshold), return it instantly from Redis. Cache hit = ~43ms instead of ~6000ms.
**Smart part:** Uses two separate vectors (query + context) to avoid false matches. A "what is NVIDIA's revenue" query won't match a "what is Tesla's revenue" query even if the context is similar.

### 4. Speculative Pre-fetching (PASTE)
**Problem:** Tool calls (web search) sit idle waiting for the LLM to finish before they're even started.
**Fix:** Watch history. If "node_search_sentiment" follows "node_analyze" 80%+ of the time across 3+ runs, fire the search request *while the LLM is still generating*. By the time the LLM finishes, the search result may already be back.
**Result:** The tool call's latency overlaps with the LLM's generation time instead of stacking after it.

---

## The Matchmaker Deck — "Tinder for Optimizations"

Before or during a run, a card deck appears showing each optimization the compiler found. For each card:
- **Swipe right / Approve** → that optimization stays active. The compiled run immediately re-runs with it included.
- **Swipe left / Reject** → that optimization is skipped. The backend actually serializes that group (adds a dependency edge), so it's not just hidden — the execution genuinely changes.

This lets a developer say "I don't trust speculative prefetching for this workflow" and see the real latency impact.

---

## The Agent Terminal

The terminal button opens a full-screen overlay. You can type:
- `arena race` — same as clicking Race
- `arena baseline` — run baseline only
- `arena compiled` — run compiled only
- `cache status` — check what's in the semantic cache
- `compile` — recompile the current workflow
- Plain English: "run the workflow and show me the results"

The backend plans these commands deterministically (no LLM needed to parse intent), then runs the exact same code the buttons do. Results stream back as SSE.

---

## The Circuit Breaker

Every LLM call has a budget pre-reserved before it starts. If the total projected spend would exceed `budget_limit_usd`:
1. The node fails with `CIRCUIT_BREAKER_TRIGGERED`
2. All nodes downstream of it are immediately halted
3. The run completes with a FAILED contract verdict

This prevents runaway costs in concurrent pipelines where multiple nodes might overspend simultaneously.

---

## External Services Connected

| Service | What it does | Where configured |
|---------|-------------|-----------------|
| **LiteLLM proxy** | Routes LLM calls to the actual model (qwen2.5-3b over a tunnel) | `LITELLM_PROXY_URL` + `OPENAI_API_KEY` in `.env` |
| **Tavily** | Real web search — `tool_io` nodes call this | `TAVILY_API_KEY` in `.env` |
| **Redis** | Stores the semantic cache (vectors + answers) | `REDIS_HOST` / `REDIS_PORT` in `.env` |
| **fastembed** | Local model that converts text to vectors for the cache | Bundled, no key needed |
| **Langfuse** | Observability — every span (node, LLM call, tool call, cache probe) is sent here | `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` in `.env` |
| **Gemini** | LLM-as-judge — checks if baseline and compiled said the same thing | `GEMINI_API_KEY` in `.env` (not set yet) |
| **SQLite** | Stores run history for PASTE speculative prefetching | Auto-created at `.synapse/paste.db` |
| **Slack** | Alerts when a run is halted by the circuit breaker | `SLACK_WEBHOOK_URL` in `.env` |

---

## Full User Journey Through the Website

### Page 1: `/` (Landing Page)

1. You land on a dark page with an ambient green glow behind everything (WebGL plasma effect)
2. The **navbar** has SYNAPSE logo, "Execution" and "Optimization" scroll anchors, and an **"Open Dashboard →"** button
3. **Hero section** — two side-by-side visuals:
   - Left: `AgentPipeline` — a single-lane serial chain, one node at a time (the slow way)
   - Right: `AgentMesh` — a 6-lane concurrent circuit board (the fast way)
4. **Telemetry block** — shows real measured numbers: 65.5% latency reduction, 31s → 10s
5. **Three pillars** — feature explanations: deterministic orchestration, parallel execution, cost optimization
6. **Steps carousel** — animated panels showing the 4 phases of the pipeline
7. **Agent rack** — isometric illustration of agents in a server rack
8. Click **"Open Dashboard →"** to go to `/dashboard`

---

### Page 2: `/dashboard` (The Arena)

**On arrival:**
- The sidebar rail appears on the left with 6 navigation items
- The top bar shows breadcrumbs + search
- The main content loads the arena

**Top bar (arena-specific):**
- Workflow selector — pick which workflow to run
- Health dot — green if backend is up, red if not
- Cache Warm toggle — turn on to pre-populate the cache before the race
- Run Baseline / Run Compiled / Race buttons
- Terminal button

**The canvas (React Flow graph):**
- Shows all nodes from the selected workflow as cards connected by animated edges
- Left side = baseline lane (serial), right side = compiled lane (DAG)
- Watch nodes light up as they run

**Left sidebar panel (Agent Roster):**
- Each agent listed with its status, live stopwatch, and stats

**Matchmaker Deck (appears after compile):**
- Cards showing optimizations — swipe or click to approve/reject

**After the race finishes:**
- Scoreboard pops up with full comparison
- Telemetry meters update with real measured values

---

### Pages 3–7: Other Dashboard Views (UI shells, no live data yet)

| Page | What you see |
|------|-------------|
| `/dashboard/history` | Table of past runs |
| `/dashboard/models` | Model names, costs, context sizes |
| `/dashboard/keys` | API key fields (masked by default, click to reveal) + Gemini judge panel |
| `/dashboard/billing` | Cost breakdown |
| `/dashboard/settings` | Workspace configuration |

Each of these shows a note that the data is staged (not connected to a real backend yet).

---

## Running the Project

```bash
# Backend
cd backend
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm run dev          # visits http://localhost:3000

# Tests
cd backend && .venv/Scripts/python -m pytest tests -q   # 169 tests
cd frontend && npx tsc --noEmit                          # type check
```

### Environment variables needed (in `backend/.env`)
```
TAVILY_API_KEY=...          # web search
OPENAI_API_KEY=...          # LiteLLM proxy auth
LITELLM_PROXY_URL=...       # your LLM tunnel
REDIS_HOST=localhost        # semantic cache
LANGFUSE_PUBLIC_KEY=...     # observability (optional)
LANGFUSE_SECRET_KEY=...     # observability (optional)
GEMINI_API_KEY=...          # LLM-as-judge (optional)
SLACK_WEBHOOK_URL=...       # alerts (optional)
```

Set `LLM_OFFLINE_MODE=true` to run everything with deterministic stubs (no real network calls, good for demos without API keys).

---

## Known Gaps (as of Phase 10)

1. **Landing page numbers are slightly stale** — shows Phase 6 numbers (57.9%, 35s→14s) instead of Phase 7 live numbers (65.5%, 31s→10s). Text-only fix needed in `Telemetry.tsx`.
2. **Gemini judge not active** — `GEMINI_API_KEY` not set. Judge is wired but reports unavailable.
3. **5 dashboard views have no backend** — History, Models, Keys, Billing, Settings show staged data.
4. **Handoff carousel unconfirmed** — The WebGL panels in the landing page carousel may render blank. Fallback: the CSS `StepsDeck` already does the same animation.
5. **`three.js` is now in the bundle** — landing route is 390 kB first load (up from 234 kB) because the carousel pulled it in.
