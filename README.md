# SYNAPSE — AI Workflow Compiler & Execution Runtime

> **The Iterators** · Bit N Build 2026 Hackathon

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-14-black?logo=next.js&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-169%20passing-brightgreen)
![Redis](https://img.shields.io/badge/Cache-Redis-DC382D?logo=redis&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-blue)

---

## What is SYNAPSE?

SYNAPSE is an **AI workflow compiler and execution runtime**. You write a multi-agent pipeline as a simple JSON file — a list of AI agents and the tools they can call — and SYNAPSE compiles it into a **Directed Acyclic Graph (DAG)**, then runs it through **four compiler optimization passes** before execution.

The result: the same workflow that takes **31 seconds naively** finishes in under **11 seconds** after compilation, with automatic caching reducing repeated queries to **43 ms**.

A live **"Race Arena"** UI shows the baseline (unoptimized) and compiled runs side-by-side so you can see the difference in real time.

---

## Live Benchmark Numbers

| Mode | Latency | Tokens | Cost | Notes |
|------|---------|--------|------|-------|
| Baseline (serial) | 31,052 ms | — | — | No optimizations |
| Compiled (cold) | 19,030 ms | — | — | DAG scheduler + PASTE cold |
| Compiled (warm PASTE) | 10,717 ms | — | — | **65.5% faster** than baseline |
| Cache hit (warm) | 43 ms | 0 | \$0.00 | Served from Redis |
| Full live run | 12,815 ms | 361 | \$0.000722 | Contract PASSED |
| Single completion | 6,027 ms | 44 | — | Live LLM |

> Contract assertions checked: `summary`, `risk_factors`, `outlook` keys all present. SLA margin: +4,283 ms.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        SYNAPSE                              │
│                                                             │
│   JSON Workflow ──► Compiler ──► Optimized DAG ──► Runner  │
│                       │                              │      │
│               4 Passes Run Here              SSE Stream     │
│                                                     │       │
│                                              Frontend UI    │
└─────────────────────────────────────────────────────────────┘

Compiler Passes (in order):
  1. DAG Builder      → parse nodes, resolve dependencies
  2. Ready-Node Scheduler → async parallelism via asyncio.TaskGroup
  3. PASTE Pre-fetcher → speculative tool calls during LLM generation
  4. Context Cache    → dual-vector semantic Redis cache
  5. DSPy Fusion      → merge adjacent LLM nodes into one request
```

---

## The Four Optimization Passes

### 1. Ready-Node DAG Scheduler

Every workflow node declares its `dependencies`. SYNAPSE builds a proper DAG and tracks each node's **in-degree** (how many upstream nodes it's waiting on). The moment all upstream nodes finish, the next node is dispatched immediately via Python's `asyncio.TaskGroup`.

This turns serial chains into parallel fans wherever the workflow allows it.

**Result:** Serial 35s → Compiled 19s (first cold run)

**Code:** [`backend/app/compiler/scheduler.py`](backend/app/compiler/scheduler.py), [`backend/app/compiler/dag.py`](backend/app/compiler/dag.py)

---

### 2. PASTE — Speculative Tool Pre-fetching

PASTE (Predictive Asynchronous Speculative Tool Execution) watches which tools each agent tends to call. It stores a **transition probability matrix** in SQLite — after 3+ observations, if `P(tool | agent) > 0.75`, SYNAPSE fires the tool request in the background *while the LLM is still generating its response*.

By the time the LLM finishes thinking, the tool result is already waiting. This hides most of the tool round-trip latency.

**Result:** Cold 19s → Warm PASTE 10.7s

**Code:** [`backend/app/runtime/paste.py`](backend/app/runtime/paste.py)

---

### 3. Context-Aware Dual-Vector Semantic Cache

Before calling an LLM, SYNAPSE computes **two separate 384-dimensional MiniLM-L6-v2 embeddings**:
- One for the **query** text
- One for the **conversation context** (what happened before)

Both are checked against Redis. If the combined similarity score is **≥ 0.88**, the cached answer is returned immediately — no LLM call needed.

This is smarter than a simple text-hash cache: semantically similar questions ("What's Apple's stock price?" / "How is Apple stock doing?") get the same cached answer.

**Result:** ~6,000 ms LLM call → ~43 ms cache hit

**Code:** [`backend/app/llm/cache.py`](backend/app/llm/cache.py)

---

### 4. DSPy Prompt Fusion

When two or more **adjacent LLM nodes** use the same model and don't share private/sensitive context with other nodes, SYNAPSE merges them into a **single API request**. The merged node returns a dictionary, and downstream nodes each receive only their slice — at zero extra token cost.

This reduces the number of API round-trips and cuts token overhead from repeated system prompts.

**Code:** [`backend/app/runtime/fusion.py`](backend/app/runtime/fusion.py)

---

## Tech Stack

### Backend
| Component | Technology |
|-----------|-----------|
| API server | Python 3.11+, FastAPI, Uvicorn |
| Data validation | Pydantic v2 |
| DAG processing | NetworkX |
| LLM routing | LiteLLM |
| Semantic embeddings | fastembed (MiniLM-L6-v2, 384-dim) |
| Semantic cache | Redis |
| Speculative pre-fetch DB | SQLite |
| Prompt optimization | DSPy-AI |
| Streaming | SSE-Starlette |
| Observability | OpenTelemetry + Langfuse |
| Alerts | Slack Webhooks |
| Web search tool | Tavily API |

### Frontend
| Component | Technology |
|-----------|-----------|
| Framework | Next.js 14 (App Router) |
| DAG visualization | React Flow (`@xyflow/react`) |
| State management | Zustand |
| Animations | GSAP |
| Styling | Tailwind CSS + shadcn/ui |
| WebGL effects | Three.js (landing carousel) |

### LLM
- Model: `openai/qwen2.5-3b-instruct` via LiteLLM proxy
- Offline demo mode: deterministic stubs (no API keys required)

---

## Project Structure

```
synapse/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes.py          # /compile, /execute/stream, /health, /workflows
│   │   ├── compiler/
│   │   │   ├── dag.py             # DAG builder and validation
│   │   │   └── scheduler.py       # Ready-node async scheduler
│   │   ├── llm/
│   │   │   ├── gateway.py         # LiteLLM wrapper, budget guard
│   │   │   └── cache.py           # Dual-vector semantic cache
│   │   ├── models/
│   │   │   └── ir.py              # WorkflowIR, WorkflowNode, CompilePlan, TestAssertions
│   │   └── runtime/
│   │       ├── runner.py          # Top-level workflow runner
│   │       ├── executor.py        # Per-node execution logic
│   │       ├── paste.py           # Speculative pre-fetching (PASTE)
│   │       ├── fusion.py          # DSPy prompt fusion
│   │       └── contract.py        # Output contract assertion checker
│   ├── tests/                     # 169 pytest tests
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── app/
│   │   ├── page.tsx               # Landing page
│   │   └── dashboard/
│   │       ├── page.tsx           # Race Arena
│   │       ├── history/           # Usage history (UI shell)
│   │       ├── models/            # Model config (UI shell)
│   │       ├── keys/              # API keys (UI shell)
│   │       ├── billing/           # Billing (UI shell)
│   │       └── settings/          # Settings (UI shell)
│   ├── components/
│   │   └── dashboard/             # Arena, Scoreboard, Roster, Meters, TopNav, Sidebar
│   └── lib/
│       └── dashboard-data.ts      # Staged demo data for UI shells
│
├── workflows/
│   └── deep_research.json         # Reference workflow (Market Intelligence)
│
├── PROJECT_EXPLAINED.md           # Plain-English system guide
├── SYNAPSE_MASTER_PRD.md          # Full product requirements document
└── CLAUDE_UPDATE.md               # Development milestone log
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+ (Node 24 supported with memory workaround — see note below)
- Redis (optional — cache falls back to in-memory dict without it)
- LiteLLM proxy (optional — set `LLM_OFFLINE_MODE=true` to skip)

> **Node 24 on Windows:** Next.js 14 can OOM on Node 24. The project includes `frontend/scripts/run-next.mjs` which automatically injects `--max-semi-space-size=16`. All `npm` scripts route through it — just use `npm run dev` normally.

---

### Environment Variables

Copy `.env.example` to `.env` in the `backend/` directory and fill in your values:

```bash
cp backend/.env.example backend/.env
```

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Live mode | API key for your LLM provider |
| `LITELLM_PROXY_URL` | Live mode | URL of your LiteLLM proxy (default: `http://localhost:4000`) |
| `TAVILY_API_KEY` | Live mode | Tavily web search API key |
| `REDIS_HOST` | Optional | Redis host (default: `localhost`) |
| `REDIS_PORT` | Optional | Redis port (default: `6379`) |
| `SEMANTIC_CACHE_SIMILARITY_THRESHOLD` | Optional | Cache hit threshold (default: `0.88`) |
| `SEMANTIC_CACHE_TTL_SECONDS` | Optional | Cache TTL (default: `3600`) |
| `LLM_OFFLINE_MODE` | Optional | `true` = use deterministic stubs, no API calls |
| `LANGFUSE_PUBLIC_KEY` | Optional | Langfuse observability public key |
| `LANGFUSE_SECRET_KEY` | Optional | Langfuse observability secret key |
| `SLACK_WEBHOOK_URL` | Optional | Slack webhook for halted-run alerts |
| `MAX_BUDGET_PER_WORKFLOW_USD` | Optional | Per-workflow budget cap (default: `$0.50`) |

---

### Running the Backend

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.

---

### Running the Frontend

```bash
cd frontend

npm install
npm run dev
```

The UI will be available at `http://localhost:3000`.

---

### Offline Demo Mode (No API Keys Required)

Set `LLM_OFFLINE_MODE=true` in `backend/.env`. This switches both the LLM gateway and the tool clients to deterministic stubs — no network calls, no API keys. The Race Arena will still run both lanes and show real timing differences from the scheduler and fusion passes.

```bash
# backend/.env
LLM_OFFLINE_MODE=true
```

---

## Reference Workflow — `deep_research.json`

The included reference workflow is an **Autonomous Market Intelligence Pipeline**. It demonstrates all four optimization passes working together.

```
User query
    │
    ▼
[node_extract_entities]   ← LLM: extracts 3 financial search terms
    │
    ├───────────────────────┬──────────────────────┐
    ▼                       ▼                      ▼
[node_search_filings]  [node_search_sentiment]  [node_search_macro]
  (SEC / EDGAR)          (press coverage)        (CPI / rates)
    │                       │                      │
    └───────────────────────┴──────────────────────┘
                            │
                            ▼
               [node_draft_findings]   ← LLM: bullet-point analysis
                            │
                            ▼
               [node_synthesize_report] ← LLM: executive brief
```

The three search nodes run **in parallel** (DAG scheduler), their Tavily calls are **pre-fetched** (PASTE), and the two final LLM nodes are candidates for **fusion**.

**Output contract** (checked after every run):
```json
{
  "required_output_keys": ["summary", "risk_factors", "outlook"],
  "min_semantic_similarity": 0.95,
  "max_acceptable_latency_ms": 15000
}
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/workflows` | List available workflow JSON files |
| `POST` | `/compile` | Compile a workflow JSON → returns `CompilePlan` |
| `POST` | `/execute/stream` | Execute a compiled workflow → SSE stream of node events |

### Example: Compile a Workflow

```bash
curl -X POST http://localhost:8000/compile \
  -H "Content-Type: application/json" \
  -d @workflows/deep_research.json
```

### Example: Stream Execution

```bash
curl -N -X POST http://localhost:8000/execute/stream \
  -H "Content-Type: application/json" \
  -d '{"workflow_id": "wf_deep_research_v1", "query": "Analyze Tesla Q3 outlook"}'
```

The SSE stream emits JSON events per node:
```json
{"node_id": "node_extract_entities", "status": "running", "elapsed_ms": 120}
{"node_id": "node_extract_entities", "status": "completed", "output": "...", "elapsed_ms": 6043}
```

---

## Running Tests

```bash
cd backend
.venv\Scripts\activate
python -m pytest tests -q
```

169 tests pass. The test suite pins `LLM_OFFLINE_MODE=true` automatically — no network or API keys needed.

### Useful Utility Scripts

```bash
# Prove the live LLM works and count tokens
python verify_live_llm.py --tasks --max-tokens 400

# Reset the PASTE transition matrix (forces cold pre-fetch)
python clean_db.py

# Delete paste.db entirely (stop backend first)
python clean_db.py --delete

# Typecheck the frontend
cd frontend && npx tsc --noEmit

# Production build (uses memory wrapper automatically)
cd frontend && npm run build
```

---

## UI Pages

| Route | Description |
|-------|-------------|
| `/` | Landing page — WebGL hero, feature overview, live telemetry numbers |
| `/dashboard` | **Race Arena** — dual React Flow canvas showing baseline vs. compiled runs side-by-side |
| `/dashboard/history` | Usage history (UI shell — staged data) |
| `/dashboard/models` | Model configuration (UI shell — staged data) |
| `/dashboard/keys` | API key management (UI shell — masked, no backend) |
| `/dashboard/billing` | Billing overview (UI shell — staged data) |
| `/dashboard/settings` | Settings (UI shell — staged data) |

### Race Arena Features
- **Dual canvas** — baseline DAG and compiled DAG run simultaneously
- **Node state colors** — cyan (running), violet (completed), emerald (cached), orange (blocking)
- **Matchmaker Deck** — workflow selector with metadata cards
- **Scoreboard** — live latency and cost comparison
- **Agent Roster** — per-node timing breakdown
- **Telemetry Meters** — latency saved, nodes fused, cache hits, parallelised nodes

---

## Guardrails & Safety

### Budget Guard
Every workflow declares a `budget_limit_usd`. The LLM gateway tracks token costs in real time and **halts the run** if the budget would be exceeded. A Slack alert fires on halt (if `SLACK_WEBHOOK_URL` is set).

### Output Contract Assertions
After execution, SYNAPSE checks the final output against the workflow's `test_assertions`:
- **Required output keys** — must all be present in the response
- **Min semantic similarity** — output must be semantically close to expected answer (MiniLM cosine similarity)
- **Max latency** — if the run took longer than allowed, the contract fails

A `contract: PASSED` / `contract: FAILED` result is included in every run summary.

### Observability
Every HTTP request, node execution, LLM completion, cache probe, and tool call is wrapped in an OpenTelemetry span and exported to Langfuse (if credentials are set). Without credentials, spans are created and timed in-process but never sent — no silent failures.

---

## Known Limitations

1. **Landing page shows Phase 6 numbers.** The hero copy cites 57.9% / 35,000ms → 14,730ms (old rehearsal figures). The real, current headline is **65.5%, 31,052ms → 10,717ms**. This is a text-only change pending update.

2. **Gemini judge is keyless.** Phase 8 wired an LLM-as-judge (Gemini) end-to-end, but it reports itself unavailable without `GEMINI_API_KEY` in `backend/.env`. The API keys dashboard panel is presentational only — it does not persist or transmit keys.

3. **Five dashboard views have no backend.** History, Models, API Keys, Billing, and Settings are frontend-only shells over `lib/dashboard-data.ts`. Each view labels itself accordingly.

4. **Landing carousel is unconfirmed on all hardware.** The `HandoffCarousel` uses WebGL (Three.js). If panels render blank, the SVG data-URI textures failed to rasterise — fall back to the existing CSS `StepsDeck`.

5. **Landing route bundle: 390 kB first load.** Three.js is pulled in by the carousel. Removing that section returns the page to ~234 kB.

6. **`LLM_OFFLINE_MODE` also governs tools.** The name is technically a misnomer — the flag disables both LLM calls and Tavily tool calls. Renaming was deferred to avoid touching `.env`, config, README, and tests simultaneously.

7. **Compiled latency is non-deterministic in live mode.** PASTE race timing varies by a few hundred ms per run on live LLMs (low tens of ms in offline mode).

8. **Anatomy explainer modal not built.** PRD 9.1 specifies an isometric compiler breakdown modal in the top bar. The Phase 9 "agent rack" on the landing page is a different figure — the top-bar modal is still pending.

---

## Team

**The Iterators**

Built for Bit N Build 2026.

---

## Hackathon Rules Compliance

- ✅ All code written during the hackathon window
- ✅ Open-source dependencies only
- ✅ No pre-built AI workflow platforms used (SYNAPSE is the platform)
- ✅ Live demo available in offline mode (no API keys required)
