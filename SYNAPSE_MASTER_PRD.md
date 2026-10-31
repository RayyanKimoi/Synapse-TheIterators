# Master Product Requirements Document (PRD)
# SYNAPSE: Intelligent AI Workflow Compiler & Execution Runtime

---

## 1. Document Metadata & Executive Overview

* **Project Title:** SYNAPSE (Intelligent AI Workflow Compiler)
* **Document Version:** 2.0.0 (Unified Production Specification)
* **System Classification:** Multi-Agent AI Workflow Compiler, Execution Runtime, & Observability Engine
* **Target Delivery Horizon:** 36-Hour Hackathon Prototype to Enterprise DevEx Infrastructure
* **Target Personas:** AI Infrastructure Engineers, Backend Architects, Platform Engineers, Hackathon Adjudicators, and Technical Executives
* **Document Status:** Authoritative Master Reference

SYNAPSE is an intelligent workflow compiler and execution runtime engineered to analyze, parallelize, and optimize multi-agent AI pipelines dynamically without compromising output correctness. Current industry orchestration frameworks—such as LangChain, CrewAI, and AutoGen—operate as imperative wrappers rather than dependency-aware execution engines. They routinely execute independent tasks sequentially, recompute semantically identical steps, compound token overhead, and introduce severe latency bottlenecks.

SYNAPSE applies proven compiler principles—specifically declarative Intermediate Representations (IR) and Directed Acyclic Graph (DAG) topological sorting—to convert sequential agent pipelines into optimized, parallelized execution graphs. Combined with a sub-millisecond semantic vector cache, speculative tool pre-fetching, prompt fusion, and a consumer-inspired Developer Experience (DevEx), SYNAPSE transforms chaotic agent pipelines into deterministic, lightning-fast execution trees.

---

## 2. Claude Code Agent Directives & Toolchain Governance

This section establishes strict operational boundaries for Claude Code executing within a VS Code workspace. These directives prevent token degradation, eliminate context pollution, and ensure deterministic implementation across the stack.

### 2.1 Whitelisted Skills and Tool Allocations

Claude Code must strictly install and invoke only the following approved skills inside `.claude/skills/`:

1. **`DietrichGebert/ponytail` (Backend Code Generation & Execution Engine):**
   * *Assigned Directory:* `.claude/skills/ponytail/`
   * *Operational Mode:* Minimalist "You Aren't Gonna Need It" (YAGNI) enforcement.
   * *Scope:* Writing lightweight, performant Python 3.11+ code for the FastAPI gateway, NetworkX graph processing, and Server-Sent Events (SSE) streaming engine without generating unused boilerplate.
2. **`nextlevelbuilder/ui-ux-pro-max-skill` (Design System & Motion Preset Engine):**
   * *Assigned Directory:* `.claude/skills/ui-ux-pro-max/`
   * *Scope:* Frontend UI design, dark-mode styling, layout architecture, and utilization of its 17 built-in GreenSock Animation Platform (GSAP) motion presets for real-time stopwatches, counters, card swipes, and particle bursts.
3. **`ui-styling` (Component Foundation):**
   * *Assigned Directory:* `.claude/skills/ui-styling/`
   * *Scope:* Direct integration and styling of shadcn/ui primitives (`Card`, `Badge`, `Button`, `Dialog`, `Progress`, `Table`, `Tabs`) tailored to dark liquid-chrome aesthetics.
4. **`wheresryan22/anatomy` (Isometric Architecture & Pitch Explainer):**
   * *Assigned Directory:* `.claude/skills/anatomy/`
   * *Scope:* Generating isometric, interactive architectural explainers via `/anatomy explain how SYNAPSE compiles and optimizes an AI workflow graph` for presentation decks and in-app interactive modal sheets.
5. **`tt-a1i/archify` (Static Codebase & Data Flow Visualization):**
   * *Assigned Directory:* `.claude/skills/archify/`
   * *Scope:* Generating ASCII schematics, data-flow sequences, and entity relationship diagrams for repository documentation.

### 2.2 Excluded Skills and Redundancy Rules

To conserve tokens and eliminate runtime confusion, the following libraries and skills are excluded from this project:
* **Exclude `Leonxlnx/taste-skill`:** Avoid automated headless browser screenshot loops that saturate context windows and waste inference tokens.
* **Exclude `open-gsd/gsd-core`:** Avoid recursive sub-agent architectures that conflict with SYNAPSE’s native workflow terminology.
* **Exclude `Graphify-Labs/graphify`:** Avoid persistent `PreToolUse` hooks that consume context on every interaction.
* **Exclude `Framer Motion` and `Anime.js`:** Eliminate secondary animation engines. All animation timelines, live counter interpolations, and card interactions must rely exclusively on GSAP via `ui-ux-pro-max-skill`.
* **Exclude `originkit.dev`:** Replaced by the curated Componentry component library.
* **Exclude `Three.js` and `StringTune`:** Avoid complex 3D math overhead; 2D node graphs powered by `@xyflow/react` and custom SVG paths deliver superior clarity and performance.

---

## 3. Comprehensive Problem Statement & Computational Bottlenecks

### 3.1 Industry Analysis: The Multi-Agent Reliability Crisis

Modern enterprise software is transitioning from single-turn chat interfaces to autonomous, multi-agent systems chaining foundation models, vector databases, and external APIs. While projections indicate that agentic systems will handle up to 80% of customer support workflows and 60% of supply chain operations by 2030, current orchestration frameworks remain structurally inefficient:
* **Sequential Latency Blocking:** Frameworks process tasks sequentially. A chain requiring three distinct retrieval operations will execute them serially, forcing cumulative task runtimes to reach 40 to 60 seconds even when no data dependencies exist between queries.
* **Severe Token Inefficiency:** Benchmarks demonstrate that hierarchical agent systems (such as CrewAI) introduce up to three times the token overhead of simpler implementations, leading to compounding API invoices.
* **Degraded Multi-Step Reliability:** On complex multi-step reasoning tasks requiring planning and backtracking, reliability drops dramatically: LangGraph successfully completes approximately 62% of complex workflows, AutoGen reaches 58%, and CrewAI manages only 54%.
* **Absence of Intermediate Caching:** LLM workloads frequently exhibit recurring query patterns. Without a semantic caching layer, every variation of a prompt triggers a complete, autoregressive inference cycle. Live API calls to frontier foundation models take between 350 ms and 7000 ms, whereas retrieving semantically equivalent responses from in-memory cache requires only 3 ms to 5 ms—a speedup exceeding 250x.

---

## 4. Feature Matrix: Baseline Requirements vs. SYNAPSE Innovations

| Capability Dimension | Baseline Hackathon Requirement | SYNAPSE Production Implementation | Net-New Value Proposition |
| :--- | :--- | :--- | :--- |
| **Workflow Ingestion** | Convert AI workflows into intermediate representations. | **Declarative JSON IR Schema** with Pydantic v2 validation. | Deterministic graph validation in under 2 ms, eliminating arbitrary AST code parsing ambiguities. |
| **Graph Optimization** | Analyze dependencies and optimize execution paths. | **NetworkX Topological Depth Scheduler**. | Mathematical partitioning of independent nodes for non-blocking concurrent dispatch via `asyncio.gather`. |
| **Semantic Caching** | Basic execution memoization. | **Vector Semantic Cache** using Redis/Valkey and local MiniLM embeddings. | Sub-millisecond response caching ($< 5\text{ ms}$) with cosine similarity thresholds ($0.85\text{ to }0.90$) and dynamic TTL. |
| **Tool Execution** | Sequential tool calls. | **Speculative Tool Pre-fetching**. | Predicts downstream tool calls during LLM token generation, driving perceived tool latency to zero. |
| **Prompt Engineering** | Static prompt pass-through. | **DSPy-Inspired Macro-Prompt Fusion**. | Merges adjacent homogeneous agent nodes to eliminate redundant round-trips and reduce KV cache footprint. |
| **Correctness & Safety** | Verify outputs against test cases. | **Contract Assertion & Invariance Suite**. | Validates schema conformance, critical entity extraction, and enforces baseline-to-compiled semantic cosine similarity $\ge 0.95$. |
| **DevEx & UI/UX** | Basic dashboard and execution metrics. | **Consumerized DevEx ("Tinder for Optimizations")**. | Visual Agent Profile Cards, swipeable optimization matches, Componentry visual accents, and an interactive side-by-side arena. |
| **Telemetry & Observability** | Execution profiling and cost estimation. | **Real-Time SSE Stream & OpenTelemetry Spans**. | Emits granular state frames every 100 ms directly to client-side Zustand stores and Langfuse tracing. |

---

## 5. System Architecture & Declarative Data Contracts

### 5.1 End-to-End System Data Flow

The SYNAPSE architecture decouples compilation, scheduling, and runtime execution from the user interface:

1. **Ingestion & Validation:** The developer or client submits a declarative workflow JSON to the FastAPI gateway via `POST /api/v1/compile`. Pydantic v2 models validate node schemas and acyclicity.
2. **Compilation & Optimization Passes:**
   * *Pass 1 (Dependency Analysis):* NetworkX constructs a directed graph $G = (V, E)$, detects cycles, and calculates the topological depth of every node.
   * *Pass 2 (Prompt Fusion):* Adjacent LLM nodes sharing common context are marked for fused execution.
   * *Pass 3 (Speculative Identification):* Downstream deterministic tools with execution likelihood $> 75\%$ are flagged for pre-fetching.
3. **Execution Runtime & Dispatch:** The client initiates execution via `POST /api/v1/execute/stream?mode=compiled`. Python's `asyncio` event loop dispatches independent node batches concurrently.
4. **Interception & Guardrails:** Outgoing requests pass through the Redis vector cache (intercepting semantically identical prompts) and the LiteLLM Proxy (enforcing spend limits, timeouts, and OpenTelemetry tracing).
5. **Telemetry Broadcast:** The backend dispatches Server-Sent Events (SSE) updates formatted as `text/event-stream` at 100 ms intervals, driving the Next.js visualizer and GSAP counters.

### 5.2 Declarative JSON Intermediate Representation (IR) Schema

The compiler processes workflows structured as explicit, acyclic JSON documents:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "workflow_id": "wf_deep_research_v1",
  "name": "Autonomous Market Intelligence Pipeline",
  "budget_limit_usd": 0.50,
  "nodes": [
    {
      "id": "node_extract_entities",
      "type": "llm_agent",
      "persona": "Taxonomy Extraction Specialist",
      "system_prompt": "Deconstruct user query into 3 targeted financial search terms.",
      "model": "ollama/qwen2.5-7b",
      "dependencies": [],
      "params": {}
    },
    {
      "id": "node_search_filings",
      "type": "tool_io",
      "tool_name": "tavily_search",
      "persona": "Regulatory Crawler",
      "system_prompt": "Query SEC EDGAR archives for 10-K filings.",
      "dependencies": ["node_extract_entities"],
      "params": { "query_vector_index": 0 }
    },
    {
      "id": "node_search_sentiment",
      "type": "tool_io",
      "tool_name": "tavily_search",
      "persona": "Market Sentiment Crawler",
      "system_prompt": "Fetch real-time financial press coverage.",
      "dependencies": ["node_extract_entities"],
      "params": { "query_vector_index": 1 }
    },
    {
      "id": "node_search_macro",
      "type": "tool_io",
      "tool_name": "tavily_search",
      "persona": "Macroeconomic Crawler",
      "system_prompt": "Retrieve interest rate projections and CPI metrics.",
      "dependencies": ["node_extract_entities"],
      "params": { "query_vector_index": 2 }
    },
    {
      "id": "node_synthesize_report",
      "type": "llm_agent",
      "persona": "Executive Briefing Synthesizer",
      "system_prompt": "Synthesize regulatory, sentiment, and macro findings into a brief.",
      "model": "ollama/qwen2.5-7b",
      "dependencies": [
        "node_search_filings",
        "node_search_sentiment",
        "node_search_macro"
      ],
      "params": {}
    }
  ],
  "test_assertions": {
    "required_output_keys": ["summary", "risk_factors", "outlook"],
    "min_semantic_similarity": 0.95,
    "max_acceptable_latency_ms": 15000
  }
}
```

---

## 6. Compiler Engine & Optimization Algorithms

### 6.1 DAG Construction & Topological Depth Partitioning

The compiler mathematically eliminates false sequential chains by mapping dependencies with NetworkX:

1. Ingest nodes and edges into directed graph $G = (V, E)$.
2. Execute cycle verification: If $\text{has\_cycle}(G) = \text{True}$, abort compilation and return HTTP 400 with cycle path details.
3. Compute the topological depth of each node $v \in V$:
   $$\text{Depth}(v) = \begin{cases} 0 & \text{if } \text{InDegree}(v) = 0 \\ \max_{u \in \text{Parents}(v)} (\text{Depth}(u)) + 1 & \text{otherwise} \end{cases}$$
4. Partition nodes into execution tiers:
   $$T_k = \{v \in V \mid \text{Depth}(v) = k\}$$
5. Dispatch tasks within tier $T_k$ concurrently using Python's `asyncio.gather(*[execute_node(n) for n in T_k])`. The critical path latency shifts from $\sum_{v \in V} \text{Latency}(v)$ to $\sum_{k} \max_{v \in T_k} \text{Latency}(v)$.

### 6.2 Sub-Millisecond Semantic Vector Caching

To intercept repetitive queries before they trigger expensive model inference, SYNAPSE integrates an in-memory vector cache backed by Redis/Valkey:

```
Input Prompt P
      │
      ▼
MiniLM-L6-v2 Embedding Vector  ───>  Redis Vector Search (HNSW / Flat)
                                                │
                 ┌──────────────────────────────┴──────────────────────────────┐
                 ▼                                                             ▼
   Cosine Similarity >= 0.88                                      Cosine Similarity < 0.88
                 │                                                             │
                 ▼                                                             ▼
     CACHE HIT (< 5 ms, $0)                                      CACHE MISS (Dispatch LLM)
     Emit Green Flash & Badge                                    Store Generated Result in Redis
```

1. **Embedding Generation:** Outgoing prompt string $P$ is converted into dense vector $\vec{v} = \text{MiniLM}(P) \in \mathbb{R}^{384}$ using `fastembed` in under 3 ms.
2. **Vector Similarity Query:** Calculate cosine similarity against cached vectors $\vec{c}_i$:
   $$\text{Sim}(\vec{v}, \vec{c}_i) = \frac{\vec{v} \cdot \vec{c}_i}{\|\vec{v}\| \|\vec{c}_i\|}$$
3. **Threshold Sweep Policy:**
   * Similarity $\ge 0.88$: Cache hit. Abort LLM call, return stored response instantly, set `is_cache_hit = true`, record latency $< 5\text{ ms}$, and consume $0\text{ tokens}$.
   * Similarity $< 0.88$: Cache miss. Forward call to the LiteLLM gateway, stream generation, and store $(P, \vec{v}, R)$ in Redis with appropriate Time-To-Live (TTL).
4. **Dynamic TTL Policy:** Real-time data tools (e.g., stock/weather APIs) receive a strict 300-second TTL; deterministic knowledge nodes receive a 24-hour TTL.

### 6.3 Speculative Tool Pre-Fetching

Sequential agent handoffs often follow predictable patterns. For example, when an entity extractor finishes parsing input, search crawlers are dispatched in $> 75\%$ of observed executions.
* **Two-Phase Adaptive Speculation:** While upstream node $N_A$ is generating tokens, SYNAPSE initiates background coroutines for high-probability downstream tools ($N_{\text{Tool}}$).
* **Verification Phase:** Upon completion of $N_A$, if the generated parameters match the pre-fetched query arguments, the results are committed immediately, reducing perceived tool latency to $0\text{ ms}$. If parameters diverge, pre-fetched results are discarded with zero side effects.

### 6.4 Prompt Fusion Optimization

When multiple adjacent micro-agents operate within the same context window, SYNAPSE merges their instructions into a unified structured prompt. This reduces total network round-trips from $N$ to $1$, preserves Key-Value (KV) cache memory on inference servers, and avoids re-evaluating repetitive system instructions.

---

## 7. Correctness Verification & Guardrails Engine

To ensure that compiler transformations never degrade output accuracy, SYNAPSE implements a strict correctness validation framework:

1. **Structural Contract Enforcement:** Compares output JSON schemas against `test_assertions.required_output_keys`. Workflows failing schema validation trigger automatic rollbacks.
2. **Deterministic Entity Extraction Check:** Verifies that critical numerical entities, dates, and currency values extracted during baseline sequential runs are fully preserved in compiled runs.
3. **Semantic Cosine Invariance Assertion:** Uses localized sentence embeddings to compare the semantic integrity of baseline output $Y_{\text{baseline}}$ and compiled output $Y_{\text{compiled}}$:
   $$\text{Sim}(Y_{\text{baseline}}, Y_{\text{compiled}}) = \frac{\vec{y}_{\text{baseline}} \cdot \vec{y}_{\text{compiled}}}{\|\vec{y}_{\text{baseline}}\| \|\vec{y}_{\text{compiled}}\|} \ge 0.95$$
4. **Financial Circuit Breakers:** Configured at the LiteLLM proxy level. If an individual workflow run exceeds `budget_limit_usd` ($0.50 default), the proxy severs outbound API calls, returns a partial result, and flags the run as `CIRCUIT_BREAKER_TRIGGERED` to prevent runaway spending.

---

## 8. Real-Time Telemetry & Server-Sent Events (SSE) Protocol

### 8.1 Node State Transition Model

Nodes transition through five deterministic states, mapped to explicit UI and telemetry attributes:

| State | Status Description | UI Visual Representation | Edge Visual Behavior | Telemetry Payload Impact |
| :--- | :--- | :--- | :--- | :--- |
| `IDLE` | Node waiting for upstream dependencies. | Slate card `#12141A`, zinc border `#27272A`. | Solid dark gray line (`#3F3F46`). | Latency: 0 ms; Tokens: 0; Cost: $0.00. |
| `RUNNING` | Active execution or model generation. | Cyan glow (`#06B6D4`), GSAP pulse ring. | Animated cyan dashes flowing forward. | Live millisecond counter incrementing. |
| `CACHED` | Prompt intercepted by vector cache. | Emerald glow (`#10B981`), lightning checkmark. | High-speed green particle burst. | Latency: $< 5\text{ ms}$; Tokens: 0; Cost: $0.00. |
| `COMPLETED` | Execution finished and validated. | Solid violet border (`#8B5CF6`), static summary. | Solid electric violet path. | Final node latency, tokens, and cost. |
| `FAILED` | Exception or safety assertion failed. | Crimson border (`#EF4444`), alert icon. | Red path, animation halted. | Error trace, circuit breaker flags. |

### 8.2 Streaming Telemetry Event Payload

The backend dispatches Server-Sent Events (SSE) formatted as `text/event-stream` at 100 ms intervals:

```json
event: telemetry_update
data: {
  "run_id": "run_c78a4b91",
  "pipeline_type": "compiled",
  "timestamp_ms": 1729482910452,
  "elapsed_pipeline_ms": 1180,
  "active_nodes": ["node_search_filings", "node_search_sentiment", "node_search_macro"],
  "node_states": {
    "node_extract_entities": {
      "status": "COMPLETED",
      "latency_ms": 1120,
      "tokens_consumed": 210,
      "cost_usd": 0.00042,
      "is_cache_hit": false
    },
    "node_search_filings": {
      "status": "RUNNING",
      "latency_ms": 60,
      "tokens_consumed": 0,
      "cost_usd": 0.0,
      "is_cache_hit": false
    },
    "node_search_sentiment": {
      "status": "CACHED",
      "latency_ms": 4,
      "tokens_consumed": 0,
      "cost_usd": 0.0,
      "is_cache_hit": true
    },
    "node_search_macro": {
      "status": "RUNNING",
      "latency_ms": 60,
      "tokens_consumed": 0,
      "cost_usd": 0.0,
      "is_cache_hit": false
    },
    "node_synthesize_report": {
      "status": "IDLE",
      "latency_ms": 0,
      "tokens_consumed": 0,
      "cost_usd": 0.0,
      "is_cache_hit": false
    }
  },
  "aggregate_metrics": {
    "total_tokens": 210,
    "total_cost_usd": 0.00042,
    "projected_cost_saved_usd": 0.0042,
    "circuit_breaker_status": "NORMAL",
    "correctness_score": 0.982
  }
}
```

---

## 9. Consumerized DevEx & Frontend UI/UX Specifications

SYNAPSE transforms complex workflow optimization into an engaging, consumer-inspired desktop experience. The UI is built using **Next.js 14**, **`@xyflow/react`**, **Tailwind CSS**, and **shadcn/ui**, styled with dark liquid-chrome aesthetics and animated with **GSAP**.

### 9.1 Layout Structure & Viewport Architecture

The desktop dashboard is partitioned into clean, functional viewports:
* **Top Navigation Bar:** Houses the workflow selector, run triggers, offline mode badge, and the trigger for the **Anatomy Isometric Explainer Modal**.
* **Hero Visualizer Header:** Utilizes Componentry’s `pixel-canvas` and `liquid-chrome` background accents combined with `annotated-text` to highlight optimization gains.
* **Left Viewport (Agent Profile Roster):** Displays active workflow agents styled as consumer profile cards with performance metrics ribbons.
* **Center-Right Viewport (Live Execution Arena):** Houses the split-screen benchmarking race track powered by synchronized React Flow canvases.
* **Floating Optimization Matchmaker:** An interactive, swipeable card deck presenting compiler optimization recommendations.
* **Footer Scoreboard:** Real-time dual stopwatches, token/dollar counters, and Trust & Safety status indicators.

### 9.2 Viewport 1: Agent Profile Cards

Each agent node is represented as an interactive card using shadcn/ui primitives and Componentry’s `flight-status-card` layout pattern:
* **Card Header:** Agent persona name, role avatar, and execution state badge (`IDLE`, `RUNNING`, `CACHED`, `COMPLETED`).
* **Agent Bio:** Collapsible drawer revealing system instructions and persona parameters.
* **Performance Telemetry Ribbon:** Replicating a flight status ribbon, showing live telemetry:
  * Average Latency ($\text{ms}$)
  * Cumulative Tokens Consumed
  * API Unit Cost ($\text{USD}$)
  * Cache Recall Rate ($\%$)

### 9.3 Viewport 2: Optimization Matchmaker ("Tinder for Optimizations")

When the compiler detects graph inefficiencies, it displays swipeable recommendation cards:
* **Card Mechanics:** Powered by GSAP drag and swipe timelines. Swiping right (or clicking Approve) applies the optimization pass; swiping left (or clicking Dismiss) retains sequential execution.
* **Opportunity Breakdown:** Clear summary cards (e.g., *"Optimization Candidate: Parallelize 3 Independent Search Tools"* or *"Prompt Fusion: Merge Synthesizer Context"*).
* **Projected Impact Display:** Highlights expected gains:
  * Latency Reduction (e.g., $-75\%$)
  * Token Savings (e.g., $-14,200\text{ tokens}$)
  * Cost Impact (e.g., $-\$0.18\text{ per run}$)

### 9.4 Viewport 3: Live Split-Screen Execution Arena ("The Race")

The central dashboard view features two side-by-side `@xyflow/react` canvases racing in real time:
* **Left Canvas (Unoptimized Baseline Pipeline):**
  * Displays nodes executing in rigid sequential order.
  * Active nodes show pulsing orange progress bars indicating blocking states.
  * Connecting edges show a single, slow particle pulse traversing the pipeline.
* **Right Canvas (SYNAPSE Compiled Pipeline):**
  * Parallel branches fire simultaneously with glowing cyan borders and particle streams.
  * When semantic cache hits occur, the node instantly flashes neon emerald (`#10B981`) with a `< 5ms Instant Hit` badge, bypassing loading states entirely.
* **Arena Footer Scoreboard:**
  * **Dual Millisecond Stopwatches:** Powered by GSAP timeline tickers, updating every 10 ms to display Baseline vs. Compiled execution duration.
  * **Dynamic Financial Counter:** Real-time ticker tracking token spend and dollar savings.
  * **Trust & Safety Badge:** Confirms system guardrails (`Budget Cap: PASS`, `Invariance Check: 98.4% PASS`).

### 9.5 Componentry & Design Toolchain Integrations

* **`shadcn/ui` Foundation:** Provides baseline structural components (`Card`, `Dialog`, `Progress`, `Badge`, `Tabs`) styled with Tailwind CSS.
* **`GSAP` Motion Engine (via `ui-ux-pro-max-skill`):** Drives all dynamic visual elements:
  * Counter interpolation for millisecond clocks and dollar tickers.
  * Node status transitions and border pulse rings.
  * Card swipe interactions in the Optimization Matchmaker.
  * Custom SVG particle velocity adjustments along React Flow edges.
* **Componentry Visual Accents:**
  * `pixel-canvas`: Interactive background grid behind the execution arena.
  * `liquid-chrome`: Background styling on top command bars and optimization cards.
  * `closing-plasma`: Transition effect displayed during workflow compilation.
  * `annotated-text`: Hover annotations explaining compiler optimization passes.
  * `flight-status-card`: Reusable layout component powering Agent Profile Card telemetry ribbons.
* **`wheresryan22/anatomy` Architecture Explainer:**
  * Interactive modal accessible via the navigation header.
  * Runs `/anatomy explain how SYNAPSE compiles and optimizes an AI workflow graph` to render an isometric explainer illustrating IR parsing, topological sorting, semantic caching, and parallel dispatching for pitch presentations.

---

## 10. Technology Stack & Environment Configuration

### 10.1 Backend Infrastructure
* **Runtime:** Python 3.11+ with `uvloop`
* **API Gateway:** FastAPI 0.110+, Uvicorn
* **Graph Mathematics:** NetworkX 3.2+
* **Validation & Schemas:** Pydantic v2.6+
* **Model Routing & Guardrails:** LiteLLM Proxy
* **Local Inference (Offline Resilience):** Ollama or LM Studio running `qwen2.5:7b` or `llama3.2:3b` via local port 11434
* **Vector Semantic Cache:** Redis 7.2+ or Valkey with RedisSearch or NumPy cosine indexer
* **Embeddings:** `fastembed` (`all-MiniLM-L6-v2`)
* **Telemetry & Streaming:** `sse-starlette` (Server-Sent Events), OpenTelemetry SDK

### 10.2 Frontend Infrastructure
* **Framework:** Next.js 14 (App Router), React 18
* **Graph Canvas:** `@xyflow/react` (React Flow 12+)
* **Component Library:** shadcn/ui via Tailwind CSS
* **Animation Engine:** GreenSock Animation Platform (GSAP)
* **Icons:** Lucide React
* **State Management:** Zustand (reactive telemetry binding)

### 10.3 Environment Configuration (`.env`)

```bash
# Gateway & Server
PORT=8000
ENVIRONMENT=development
CORS_ORIGIN=http://localhost:3000

# LLM Gateway & Local Inference
LITELLM_PROXY_URL=http://localhost:4000
LOCAL_OLLAMA_URL=http://localhost:11434
OPENAI_API_KEY=sk-placeholder-demo-key
TAVILY_API_KEY=tvly-placeholder-demo-key

# Memory & Semantic Caching
REDIS_HOST=localhost
REDIS_PORT=6379
SEMANTIC_CACHE_SIMILARITY_THRESHOLD=0.88
SEMANTIC_CACHE_TTL_SECONDS=3600

# System Guardrails
MAX_BUDGET_PER_WORKFLOW_USD=0.50
MAX_CONCURRENT_TASKS=8
```

---

## 11. 36-Hour Hackathon Execution Blueprint

To guarantee a fully functional, highly polished prototype within 36 hours, engineering tasks are partitioned into six structured phases:

### Phase 1: Foundation, Schemas & Telemetry Stream (Hours 00–06)
* Scaffold Python 3.11+ environment with FastAPI, Pydantic v2 IR schemas, and NetworkX.
* Implement LiteLLM client with offline Ollama routing and deterministic mock fallbacks.
* Build `app/api/routes.py` with `POST /api/v1/compile` and `POST /api/v1/execute/stream` utilizing `sse-starlette`.
* Create reference 5-node research workflow (`workflows/deep_research.json`).

### Phase 2: Frontend Scaffolding & Arena Architecture (Hours 06–14)
* Scaffold Next.js 14 App Router project with Tailwind CSS and shadcn/ui primitives.
* Implement dual-canvas React Flow arena with custom agent node components and animated SVG edge paths.
* Build client-side SSE hook (`useWorkflowExecution`) binding streaming events directly to a Zustand store.

### Phase 3: Compiler Optimization Engine (Hours 14–20)
* Implement NetworkX topological depth scheduler to group independent nodes into parallel execution tiers.
* Build async execution engine running parallel tasks via `asyncio.gather`.
* Implement speculative tool pre-fetch dispatcher and prompt fusion logic.

### Phase 4: Sub-Millisecond Semantic Vector Cache (Hours 20–26)
* Configure local Redis/Valkey instance with `fastembed` (`all-MiniLM-L6-v2`).
* Implement prompt interception layer with cosine similarity matching ($0.85\text{ to }0.90$) and dynamic TTL policies.
* Verify sub-5 ms cache returns and 0-token execution tracking.

### Phase 5: DevEx Gamification & Visual Polish (Hours 26–31)
* Build the Optimization Matchmaker swipe deck with GSAP drag and swipe gestures.
* Implement Agent Profile Cards featuring `flight-status-card` telemetry ribbons.
* Integrate Componentry visual components (`pixel-canvas`, `liquid-chrome`, `closing-plasma`, `annotated-text`).
* Embed `wheresryan22/anatomy` isometric architecture explainer modal.

### Phase 6: Verification, Pitch Hardening & Rehearsal (Hours 31–36)
* Run output correctness suite (verifying schema conformance and semantic cosine similarity $\ge 0.95$).
* Pre-seed Redis cache with demo query vectors to guarantee sub-second execution on stage.
* Rehearse the 3-minute presentation script against local models to ensure complete immunity to venue network issues.

---

## 12. 3-Minute Live Hackathon Demonstration Script

The live demonstration follows a strict narrative arc designed to prove architectural sophistication and commercial value within 180 seconds:

* **Act 1: The Crisis (0:00 – 0:45):**
  * Load the baseline multi-agent market research workflow. Hit "Execute Baseline".
  * Direct adjudicators' attention to the left canvas: The workflow crawls serially through three independent web crawls.
  * Point to the live clock reaching 35+ seconds and the dollar ticker accumulating token costs.
  * *Speaker Narrative:* "Current agent frameworks execute blindly in sequential loops. At enterprise scale, this latency wastes computational budget and degrades user experience".
* **Act 2: The Compiler & DevEx Matchmaker (0:45 – 1:15):**
  * Switch to the SYNAPSE compiler interface.
  * An Optimization Match card slides in: *"3 Independent I/O Tasks Detected. Parallelize?"* Swipe right to approve.
  * Open the **Anatomy Isometric Explainer Modal** to show the underlying topological sort and DAG restructuring.
  * *Speaker Narrative:* "SYNAPSE treats agent workflows like compiled code. We restructure messy scripts into dependency-aware execution trees with consumerized simplicity".
* **Act 3: The Live Arena Race (1:15 – 2:15):**
  * Trigger "Run Arena Race". Both graphs execute side-by-side.
  * The baseline graph stalls on sequential steps, while the SYNAPSE-compiled graph fires all three crawler nodes concurrently.
  * The compiled pipeline finishes in 8 seconds (a 75% latency reduction), while output correctness passes at 98.4%.
* **Act 4: The Sub-Millisecond Knockout (2:15 – 3:00):**
  * Re-run the compiled workflow, submitting a semantically paraphrased query.
  * The Redis semantic cache triggers instantly: Upstream crawler nodes flash vibrant emerald checkmarks in 4 ms, bypassing external network calls.
  * Total pipeline duration drops from 8 seconds to 380 ms—a 99% overall speedup consuming 0 new tokens.
  * *Speaker Narrative:* "Sub-millisecond semantic retrieval combined with graph compilation. This is the execution runtime required for the next generation of autonomous enterprise AI".

---

## 13. Production Scaling & Enterprise Startup Roadmap

While the hackathon prototype executes locally, SYNAPSE is architected to scale into an enterprise-grade infrastructure platform:

1. **Distributed Task Orchestration:** Offload DAG node execution from the local `asyncio` event loop to distributed task clusters running Celery, Ray, or Apache Kafka for high-concurrency execution across multi-node GPU clusters.
2. **Multi-Tenant Cryptographic Cache Isolation:** Implement tenant-isolated vector namespaces within Redis to prevent cross-organization prompt leakage and enforce strict enterprise compliance.
3. **Cross-Request KV Cache Reuse:** Integrate serving frameworks such as SGLang with RadixAttention to reuse KV cache states across concurrent enterprise user sessions, further reducing Time to First Token (TTFT) and inference compute costs.