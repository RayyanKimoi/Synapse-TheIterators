# SYNAPSE Project Status & Claude Update Log

## Current Status: live end-to-end, landing page shipped, judge unwired
**Date:** November 2026
**Overall Progress:** The Tavily blocker from the previous entry is closed — a
real key is configured and the reference workflow completes live, tools and
all. Observability (OTel -> Langfuse) landed. A second contributor added an
LSH-prefiltered cache, an LLM-as-judge equivalence check, and an in-dashboard
agent terminal; their key is not yet set, so the judge is wired but inert. A
Relay-inspired marketing landing page now sits at `/`, and the execution arena
has been rehoused inside a six-view dashboard shell at `/dashboard` — its
behaviour unchanged, five of the six views still UI shells with no endpoint
behind them. 169 backend tests pass; all seven Next.js routes build clean.

### Completed & Locked Milestones
* **Phase 1 (Legacy):** Backend scaffolded. SSE telemetry and IR schemas are locked and stable.
* **Phase 2 (Functionality):** Next.js scaffolded. React Flow and Zustand are successfully consuming the SSE stream. GSAP counters are functioning.
* **Skill Governance:** Banned skills removed (`taste-skill`, `gsd-core`, `graphify` — including graphify's `PreToolUse` hooks and its `CLAUDE.md` rule injections). `anatomy`, `ponytail`, `ui-ux-pro-max`, `ui-styling`, and `archify` are active.
* **Phase 3a — V2 Ready-Node Scheduler (VERIFIED):**
  * `compiler/scheduler.py` added: `asyncio.Queue` + `asyncio.TaskGroup` worker pool bounded by `max_concurrent_tasks`. Nodes carry an `in_degree` countdown; on completion children are decremented and any child hitting zero is dispatched instantly.
  * Depth-tiering demoted to layout only. `dag.execution_tiers` renamed `dag.layout_tiers`; `topological_depths` is now explicitly a canvas-column label and never gates dispatch.
  * `runtime/profile.py` tier-barrier cursor (`cursor = max(tier ends)`) deleted. Node placement now comes from `scheduler.ready_node_timings` (start = max of own parents' ends).
  * The SSE stream (`runtime/runner.py`, formerly `mock_runner.py`) is driven by the live scheduler, not a replayed schedule. Baseline runs the same engine over a chain graph, so the arena race compares two dispatch topologies rather than two formulas.
  * `max_concurrent_tasks` is no longer dead config; `CompilePlan` now exposes `node_in_degrees` and `max_concurrency`.
  * **Verification:** on an asymmetric DAG, ready-node dispatches a node 8000 ms earlier than depth-tiering. Live pool shows real concurrency (peak in-flight > 1).
  * **SSE contract unchanged** — `TelemetryFrame` / `RunSummary` field names and the `IDLE/RUNNING/CACHED/COMPLETED/FAILED` vocabulary are untouched.
  * ⚠️ The latency figures recorded here originally (compiled 8796 ms, warm-cache 358 ms) were produced by the `0.55`/`0.18` mock multipliers and **no longer apply.** Current measured figures are in *Arena Numbers* below.

* **Phase 5 — UI/UX Overhaul (VERIFIED IN BROWSER):**
  * Design system rebuilt in `globals.css`: layered radial lighting, grain, animated liquid-chrome sheen, `.surface` elevation, `.ticker` instrument type, WCAG 2.2 focus rings, and edge-flow keyframes. Added `--state-blocking` (orange) for the baseline lane.
  * `CustomEdge.tsx` (new): particles ride the real path geometry via `getPointAtLength` — slow single particle on baseline, steady flow on compiled, 3-particle high-velocity emerald burst on cache hit.
  * `MatchmakerDeck.tsx` (new): the "Tinder for optimizations" deck. Pointer-event drag + GSAP (no plugin dependency), elastic snap-back, approve/reject buttons so the gesture is keyboard-reachable. Auto-collapses to a pill when a run starts.
  * `AgentNode`, `AgentProfileCard`, `AgentRoster`, `RaceArena`, `TopNav`, `Scoreboard` restyled: gradient avatar rings, telemetry ribbons, blocking-stripe indicator, lightning HIT badges, `00:00.000` DOM-direct GSAP stopwatches, trust badges.
  * **Copy drift fixed:** "N topological tiers" is gone from `TopNav.tsx` and `RaceArena.tsx`, replaced with Ready-Node / dependency-graph phrasing.
  * **Verification:** typecheck clean, production build clean, zero console/page errors.
  * ⚠️ The browser walkthrough was recorded against the old mocked timings (`00:08.796`, `00:00.358`, 99.0% saved). Those specific readouts are stale; the UI itself is unchanged and still renders whatever the stream sends. **The arena has not been re-verified in a browser since the V3 passes landed.**

* **Phase 6a — V3 Phase 1 wiring (VERIFIED):**
  * LLM nodes route through `llm/gateway.py`. `RunBudget` reserves each call's worst case before it is sent and settles the actual cost, so nodes dispatched concurrently cannot jointly overspend. A trip raises `HaltBranch`, which severs every descendant via `nx.descendants` and surfaces as `CIRCUIT_BREAKER_TRIGGERED` in the SSE aggregate.
  * `runtime/contract.py` evaluates the IR's `test_assertions` after the last node terminates: `required_output_keys` are checked against the merged sink payload, and the verdict rides the final frame plus `run_complete`.
  * `semantic_cache_similarity_threshold` is wired from `config.py` through `Guardrails.resolve` into the admission check. The hardcoded `0.982` invariance score is gone.

* **Phase 6b — Context-Aware Semantic Cache (VERIFIED, incl. live Redis):**
  * `llm/cache.py`: each prompt is embedded as **two** vectors — the user query and the upstream context — and **both** must clear the threshold. One combined vector does not work: a node deep in the graph carries far more context than query text, so a long shared context swamped the cosine and two genuinely different questions scored as a match. This was caught serving a Tesla answer for an NVIDIA query.
  * fastembed `all-MiniLM-L6-v2`, 384-dim, batched into one encoder call per probe (two separate calls cost ~7 ms and pushed a hit past the latency it exists to avoid). Measured discrimination: 0.98 paraphrase, 0.30 different topic, 1.00 exact.
  * **Multidimensional pre-flight validation** via `node_namespace()`: model, system prompt, tool name, params and `side_effect` are hashed into the cache key, so an entry is unreachable unless all of them are byte-identical. Similarity only ever decides whether the *question* matched.
  * Threshold held inside the PRD's 0.85–0.90 band at the config boundary. Dynamic TTL: 300 s for tool nodes, 24 h for deterministic reasoning.
  * Redis-backed with an in-memory fallback decided on first use. **Verified against a live container:** bit-exact 384-float round trips, 24 concurrent probes in 137 ms, TTLs landing at 300/86400 s, Redis-side expiry honoured.
  * **Resilience fix:** socket timeouts do not bound redis-py's internal retry/backoff, so a container that dropped mid-run took **14.76 s** to be declared dead. `asyncio.wait_for` now caps every call → **1.52 s**, and a failed write falls into memory instead of being lost.
  * `cache_warm` no longer fakes anything: it primes by genuinely executing the graph once with simulated latency collapsed, then leaves the terminal node cold so the arena keeps a visible finish line and `total_elapsed_ms` is never 0.

* **Phase 6c — PASTE Speculative Pre-fetching (VERIFIED):**
  * `runtime/paste.py`: SQLite transition matrix over observed runs. `P(target|source) = hits/runs(source)`, gate **strictly > 0.75**, with a `MIN_OBSERVATIONS = 3` floor so a single history cannot authorise speculation. All statements run off the event loop via `asyncio.to_thread`.
  * The executor fires eligible tool requests **before** awaiting the gateway, so the round trip overlaps the decode. `_run_tool` awaits the in-flight task and reports the **measured** remainder. `aclose()` cancels speculations nothing collected.
  * Never speculates a `side_effect` node, an LLM node, or anything in the baseline pipeline.
  * **`SPECULATIVE_PREFETCH_FACTOR = 0.18` deleted.** Traced live to prove the overlap is real: `node_search_filings` finished at t=61.9 ms while the scheduler only asked for it at t=63.5 ms → 0 ms remaining, genuinely complete during generation; `node_search_sentiment` was slower and correctly still owed 1605 ms.

* **Phase 6d — DSPy-Assisted Prompt Fusion (VERIFIED):**
  * `runtime/fusion.py` merges maximal chains of adjacent LLM nodes that are **private** (producer feeds only the consumer, consumer depends only on the producer), **read-only**, and on the **same model**, into one DSPy signature with one output field per node. The leader issues a single request and keeps each member's slice; followers cost a dict lookup and book zero tokens.
  * Execution deliberately stays on `llm/gateway.py`. Routing through DSPy's own LM would bypass the budget circuit breaker, the offline path and the cost accounting.
  * `side_effect: bool` added to `WorkflowNode` (the field flagged as missing in the previous log entry).
  * **`PROMPT_FUSION_FACTOR = 0.55` deleted.** It was firing on *fan-in* (`deps > 1`), not adjacency — it had been measuring the wrong thing entirely.
  * **Robustness fix:** a group whose merged response could not be parsed used to hand its followers an empty string and report them `COMPLETED`. A real qwen2.5-3b dropped the closing brace of otherwise-valid JSON and that was enough. The group now verifies every member's field is present and non-empty, and otherwise abandons fusion for that run and lets each member make its own call.
  * Live compliance: **2 of 3 runs fuse into one call; the third falls back** — both members return real content either way.

* **Phase 6e — Live LLM + Zero-Mock Audit (VERIFIED):**
  * `verify_live_llm.py` (new, standalone — imports nothing from `app`, so a pass is evidence about the tunnel rather than about SYNAPSE). Prints the verbatim generated text and a token tally for cross-checking against the server's own counters. `--tasks` sends three real token-burning jobs; `--max-tokens`, `--raw` and positional prompts supported.
  * `clean_db.py` (new): resets the PASTE matrix to cold. Default **empties the tables**, which works while the backend holds the SQLite handle; `--delete` removes the file. No process can force another process's handle closed, which is why emptying is the mode that actually works on Windows. Adds `TransitionMatrix.close()` / `reset()`.
  * **Gateway auth fix:** the gateway never sent an `api_key`, so any authenticating proxy answered 401 and the offline path turned that into a mock — the `litellm_proxy` branch had *never once succeeded*, and the failure looked like an outage rather than a missing credential.
  * **No fabricated completions:** a live call that fails now raises `LLMUnavailableError` → `HaltBranch` → a visible FAILED node. Previously the mock was the fallback for a missing litellm, an unreachable proxy and *any* exception, so a dead tunnel produced confident fake answers that the contract check, the cache and the arena all treated as real.
  * **Real tool clients:** `runtime/tools.py` makes the actual Tavily call. The `{"status": "offline_stub"}` payload and its 8.5 s simulated delay are gone from the live path. A tool that cannot run fails its node rather than substituting a result.
  * `llm_offline_mode` now governs the tool clients as well as the model and **defaults to `false`**. It is the single switch between "simulate everything deterministically, touch no network" (what the test suite pins) and the live demo.
  * `workflows/deep_research.json` declares `openai/qwen2.5-3b-instruct`.
  * Frontend `OptimizationCandidate` union and `MatchmakerDeck` gained `speculative_prefetch`, keyed through a `Record` over every kind so a future pass cannot inherit another pass's icon.

* **Phase 7 — Tavily Unblocked, Fusable Demo Pair, Observability Live (VERIFIED):**
  * **The blocker is closed.** A real `TAVILY_API_KEY` is set, calls go out over `httpx` with Bearer auth (the credential stays out of the request body and out of anything that logs one), and the reference workflow completes a live run start to finish — tools included.
  * `node_synthesize_report` split into `node_draft_findings` → `node_synthesize_report`: a private, read-only, same-model pair, which is exactly what Phase 6d's fusion pass requires. The demo workflow is now 6 nodes, depth 3, 7 edges, and actually exercises fusion instead of only `test_phase4_fusion.py`.
  * **Two real defects the split surfaced:**
    1. A fused terminal node had its output flattened to one string field, so the sink stopped emitting `required_output_keys` and `final_output` came back empty — fusion silently broke the IR contract. `FusionGroup.fields` now maps each member to the field *names* it owns, so the merged signature is `query, context -> node_draft_findings, summary, risk_factors, outlook` and the contract check still finds what it needs.
    2. A fused leader served from the semantic cache never made the merged call, so its followers collected nothing and returned empty. A follower now takes the fused path only when its slice is genuinely waiting, and otherwise earns its own answer.
  * **Observability (PRD Phase 4) landed:** `app/observability.py` — an OTel tracer provider exporting to Langfuse over OTLP (Basic auth from the key pair), `BatchSpanProcessor` so every export runs on a background thread and the SSE stream never waits on the collector. Missing packages, missing credentials or a dead collector all degrade to no-op spans — telemetry about a pipeline must not break it.
  * Instrumented: one span per HTTP request (so a run is one trace), per node execution, per gateway completion, per cache probe, per tool call. Attributes cover tokens, cost, source, cache hit + measured similarity, budget spent/tripped, tool result counts and whether a tool was simulated. Verified with a console exporter: 17 spans for one compiled run, carrying real Tavily latencies (2562/3137/3886 ms) and `source=tool_prefetched` where PASTE hid the call.
  * `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http` and `langfuse` are now in `requirements.txt` — the previous entry's gap is closed.
  * **Live benchmark, real 3B model over the tunnel + real Tavily:** baseline (serial) 31 052 ms / 3 LLM calls / 5454 tok / $0.0109; compiled, cold matrix 15 266 ms (50.8%, 2 LLM calls, fused); compiled, warm PASTE 10 717 ms (65.5%, contract PASSED, SLA margin **+4283 ms**). Real tools move the margin from +270 ms to +4283 ms, so the previous entry's recommendation to raise `max_acceptable_latency_ms` no longer applies. These are live network numbers and will vary run to run.
  * 119 tests passing at this point.

* **Phase 8 — LSH-Prefiltered Cache, LLM-as-Judge, Agent Terminal, Budget Burn (second contributor, VERIFIED by test suite):**
  * `llm/lsh.py` (new): random-hyperplane SimHash over the cache's embeddings — each vector reduced to a 256-bit signature, so comparing two entries is one XOR and one popcount. Used strictly as a *prefilter*: an entry whose Hamming distance is inconsistent with the admission threshold is skipped without computing its exact cosine (on Redis, without fetching its vectors at all). Admission is still decided by the exact cosine, so a hit is exactly as trustworthy as before — this only prunes what gets checked. The cut-off is a statistical bound tuned so a genuine match is pruned with probability on the order of 1e-6 per half.
  * `llm/judge.py` (new): an independent model (Gemini) judges whether the compiled pipeline's output still says what the baseline said. The run contract already checks structure, latency and cache-admission similarity — none of which look at what the two pipelines actually *said*, and prompt fusion or a cache hit can drift the answer while every structural check still passes. Runs **both directions concurrently** (baseline→compiled catches drops/changes, compiled→baseline catches additions) and calls it equivalent only when both agree. No key, no verdict — it reports itself unavailable rather than inventing one, and skips offline-mock output on purpose (`is_simulated`), where "the same answer" would be comparing placeholders. New settings: `gemini_api_key`, `judge_model` (`gemini-3.5-flash`), `judge_timeout_s`. **`GEMINI_API_KEY` is not set in this environment — the judge is wired but currently reports unavailable.**
  * `agent/terminal.py` (new, 746 lines): an in-dashboard terminal — commands or plain English, planned into steps that run against the *real* compiler, runtime and cache, not a separate mock path. Planning is deliberately deterministic (intent read from a fixed vocabulary, not asked of an LLM) so the terminal works with no model behind the gateway, same as the rest of the offline path. Each step calls the same code the HTTP API calls: `compile` is the real planner, `run`/`race` are real executions through `stream_telemetry`, `cache` reads the live semantic cache. New endpoint `POST /api/v1/agent/run`, SSE, POST rather than GET because a terminal line can be long and carry quotes — read client-side with `fetch()` instead of `EventSource`.
  * `frontend/components/AgentTerminal.tsx` (new) wired into `TopNav` via a new **Terminal** button; `arena …` commands in the terminal drive the same runs as the TopNav buttons, honouring the cache-warm toggle and every pass rejected in the Matchmaker.
  * `frontend/components/BudgetBurn.tsx` (new) + `lib/budget.ts`: pure warn/breaker threshold functions (80% / 100% of `budget_limit_usd`), testable in isolation from rendering. `AggregateMetrics.budget_limit_usd` added backend-side (the IR's `budget_limit_usd` clamped to the deployment ceiling) so a client's "% of budget" matches what the circuit breaker actually enforces.
  * New tests: `test_agent_terminal.py`, `test_judge.py`, `test_lsh.py`, `test_budget_telemetry.py`. **169 tests passing** (118 → 169 across this and the prior phase).

* **Phase 9 — Landing Page + Merge (my work, VERIFIED):**
  * New marketing landing page at `app/page.tsx`: hero (a single-agent pipeline vs. a six-lane concurrent `circuit-board` mesh), a telemetry block (stat tiles, meters, a baseline-vs-compiled emphasis chart — every figure a measured run from this document, not a generated series), an isometric "agent rack" figure built by `scripts/anatomy/build-rack.mjs` (passes its line-end check at 0 of 465 floating ends), and a `closing-plasma` ambient field. Typography: Inter / Montserrat / Playfair Display via `next/font`.
  * The execution arena moved unchanged to `app/dashboard/page.tsx`.
  * Three `@componentry` packages (`closing-plasma`, `circuit-board`, `flight-status-card`) are live on the page; a fourth (`liquid-glass-carousel`) is installed but unused, so `three` sits in `package.json` but is not in the shipped bundle. **`framer-motion` and `three` are now dependencies, both listed under the master PRD's Explicit Exclusions** — the governance table is stale and needs a decision.
  * `next.config.mjs` reads `distDir` from `NEXT_DIST_DIR` so a verification build can never overwrite a running dev server's `.next` (this is what caused a false "build is broken" 500 earlier — the dev server was serving stale dev chunks against a production `.next`; the fix is environmental, not a code bug).
  * **The merge:** the only real conflict with Phase 8's commit was `frontend/app/page.tsx` itself — Phase 8 added the Terminal wiring to the file this phase relocated to `/dashboard`. Resolved by taking the landing page for `app/page.tsx` and the Phase-8 dashboard (with its Terminal button intact) for `app/dashboard/page.tsx`; `git diff` against Phase 8's commit confirms `backend/` is byte-identical. Rebased cleanly, no force push, linear history.

* **Phase 10 — "Neon Void" Design System + Dashboard Shell (frontend only, PARTLY VERIFIED):**
  * **The reported 500s were not a code defect and are already closed.** The three failing URLs (`layout.css`, `main-app.js`, `app-pages-internals.js`) were dev-only chunks missing because a `next build` had overwritten the running dev server's `.next` with a *production* build. All four URLs now return 200. The permanent guard is Phase 9's `NEXT_DIST_DIR`; every verification build in this phase went to `.next-verify` and the dev server was never touched. **No CSS import, Tailwind directive or component export was at fault — do not go looking for one.**
  * **Neon Void surface language** (`globals.css`): `--void` dropped to pitch black (`0 0% 0%`) with `--surface` at `#050505`. New utilities — `.void-card` (frosted gradient + `backdrop-blur(18px)` + a 1px `white/10` hairline), `.void-card-hover` (hairline picks up the lime accent plus a soft bloom), `.void-rule`, `.void-input` (lime focus ring), and `.dot-ok/.dot-wait/.dot-fail/.dot-idle` for ledger status.
  * **Dashboard shell** (`app/dashboard/layout.tsx`): a slim collapsible rail plus a global top bar, wrapping all six views so the shell never re-mounts between them. Navigation is **real routes, not tab state**, so every view deep-links and the back button behaves.
    * `components/dashboard/icons.tsx`: hand-drawn line-art glyphs on one 24-grid (racing lanes for the arena, a stacked ledger, a pinned die for models) rather than a stock icon set.
    * `Sidebar.tsx`: collapse state persisted to `localStorage` behind try/catch, restored after mount so server and client first paint agree; active route gets the lime pill, and `/dashboard` is matched exactly so it does not light up for every child.
    * `DashTopBar.tsx`: breadcrumbs, a global search with a `/` hotkey (suppressed while typing), and a workspace selector with click-away plus Escape.
  * **Six views:**
    * **Analytics** — the existing arena, unchanged in behaviour. Its wrapper went from `h-screen <main>` to a `div` inside the shell. New `TelemetryMeters.tsx` strip above it reads the **real** telemetry store: latency saved (measured once both lanes finish, planner projection until then), nodes fused, cache hits and parallelised nodes, each a meter against its limit and each captioned with which of the two it is showing.
    * **Usage history, Models, API keys, Billing, Settings** — UI shells. Every invented value is isolated in `lib/dashboard-data.ts` so it is obvious what is staged, and each view carries a visible note saying it has no endpoint behind it. The API keys view masks every field by default with per-field reveal, and gives the LLM-as-a-judge its own accented panel (Phase 8's judge, still keyless).
  * **`TopNav.tsx` retuned, className-only.** The redundant SYNAPSE wordmark came out (the sidebar carries it now) and the chrome moved to `.void-card` + lime. **The PRD 8.1 node-state vocabulary — cyan running, violet completed, emerald cached, orange blocking — was deliberately left alone**, since it is a documented spec and Phase 8 owns that file. No props or Terminal wiring were touched.
  * **Landing:** `HandoffCarousel.tsx` mounts the previously-unused `@componentry/liquid-glass-carousel`. Its panels are WebGL textures, so each of the six handoff cards is **drawn here as an SVG and handed over as a data URI** — no stock photography and no network fetch, unlike the component's Unsplash defaults. The copy is restated in an `sr-only` list because the carousel paints to a canvas.
  * **Cost:** mounting the carousel finally pulls `three` into the bundle — the landing route went **109 kB → 252 kB** (390 kB first load). That is the price of this one section.
  * **Verified:** typecheck clean; all seven routes build and return 200; no horizontal overflow at 1440; the shell, meters, keys and billing views confirmed by screenshot.
  * ⚠️ **Not verified:** the carousel's panels were never confirmed rendering. WebGL initialises and the shader compiles (with benign HLSL `X3595` derivative warnings), but whether `THREE.TextureLoader` actually rasterises the SVG data URIs was not checked before this entry was written. **If the panels come up blank, that is the cause** — rasterise the cards to PNG, or fall back to the CSS `StepsDeck`, which already does the slide-in-and-stack behaviour.

### Arena Numbers (rehearsal profile, `LLM_OFFLINE_MODE=true`, measured not projected)
| Run | Latency | Notes |
|---|---|---|
| Baseline (serial chain) | 35 043 ms | unchanged |
| Compiled, cold matrix | 19 030 ms | parallelism only — **over the 15 s SLA** |
| Compiled, warm PASTE | 14 730 ms | 57.9% reduction, SLA margin **+270 ms** |
| Warm semantic cache | 5 075 ms | 4/5 hits, invariance 1.0, live sink |
| Planner projection (warm) | 14 760 ms | agrees with the measured run to **0.2%** |

Projection and runtime agree because both compute the PASTE overlap identically.
Optimization candidates emitted: `parallelize`, `speculative_prefetch`.

### Live Numbers (`LLM_OFFLINE_MODE=false`, real tunneled model)
* Single gateway completion: `source=litellm_proxy`, no fallback, 44 tok, 6027 ms.
* Full reference workflow before the tool nodes were made real: 12 815 ms, 2 real proxy calls, 361 tok, $0.000722, **contract passed** — the real model honoured the sink's `required_output_keys` and all three keys parsed.
* Repeated query: 43 ms, 5/5 served from Redis, 0 tok, invariance 1.0.
* `verify_live_llm.py --tasks --max-tokens 400`: 3 calls, 167 prompt + 553 completion = **720 tokens**, 14.4 s; task 1 returned `finish=length`.

### Known Gaps & Open Decisions
1. **Landing page markets the stale rehearsal numbers.** `app/page.tsx` and `Telemetry.tsx` cite 57.9% / 35 000 ms → 14 730 ms (the Phase 6 rehearsal-profile figures) because they were written before Phase 7's live benchmark landed. The real, current headline is **65.5%, 31 052 ms → 10 717 ms**, contract PASSED, SLA margin +4283 ms. The copy needs updating before this is presented — this is a text change, not a rebuild.
2. **`GEMINI_API_KEY` is not set.** Phase 8's LLM-as-judge is wired end to end (both directions, concurrent) but reports itself unavailable with no key. The API keys view now has a dedicated panel for it, but that panel is presentational — it does not persist or transmit anything, so the key still has to go into `backend/.env`.
2b. **Five dashboard views have no backend.** Usage history, Models, API keys, Billing and Settings are interfaces over `lib/dashboard-data.ts`. Each says so on screen. Wiring any of them needs endpoints that do not exist yet — and that is backend work, which this phase was scoped out of.
2c. **The handoff carousel is unconfirmed.** Its panels were never seen rendering (see Phase 10). Check it before presenting; the fallback is the existing CSS `StepsDeck`.
2d. **The landing route is now 390 kB first load** (252 kB route), up from 234 kB, because mounting the carousel pulls in `three`. Dropping that one section returns the page to its former weight.
3. **PRD governance is stale.** The master PRD's Explicit Exclusions table bans Framer Motion and Three.js; both are now dependencies, and as of Phase 10 `three` is actually *shipped* (the carousel mounts it). Either update the PRD or reimplement `circuit-board`, `flight-status-card` and `liquid-glass-carousel` on GSAP — this needs a decision, not more code.
4. **Compiled latency is no longer deterministic.** PASTE reports measured race timing, so the determinism test now covers baseline latency and compiled *spend*; the compiled clock moves by a few hundred ms (live) or low tens of ms (offline) per run.
5. **Dashboard UI spot-checked, not fully re-verified.** The merge confirmed both routes build, both return 200, and the Terminal button renders in `TopNav` with a clean console — but node-state animations, the Matchmaker deck and the `speculative_prefetch` card are still only verified by payload shape and typecheck, not watched running in a browser.
6. **Anatomy explainer modal (not built):** PRD 9.1 calls for an isometric compiler breakdown in the top bar via the `anatomy` skill. Phase 9 built a different anatomy figure (the "agent rack") for the landing page's right rail, not this modal — the top-bar explainer is still unbuilt.
7. **Still simulated, deliberately:** `profile.py`'s hash-seeded latency/token model. It no longer sits in the execution path — it feeds only the planner's *projections* (`baseline_estimate` / `compiled_estimate`), the pre-call budget reservation, and the cost fallback for a self-hosted model litellm cannot price.
8. **`llm_offline_mode` is now a misnomer** — it governs tools too. Renaming touches `.env`, config, README and tests, so it was left alone.

### Observability (PRD Phase 4) — LIVE (Phase 7)
`app/observability.py`: OTel tracer provider exporting to Langfuse over OTLP,
spans on every HTTP request, node execution, gateway completion, cache probe
and tool call. `opentelemetry-api`, `opentelemetry-sdk`,
`opentelemetry-exporter-otlp-proto-http` and `langfuse` are in
`requirements.txt`. Degrades to no-op spans with no credentials — see Phase 7
above for the verified span count and attributes.

### Environment Note (Windows + Node 24)
Next 14 crashes with `FATAL ERROR: Committing semi space failed` on Node 24, especially under memory pressure. `frontend/scripts/run-next.mjs` wraps the Next CLI and injects `--max-semi-space-size=16` via `NODE_OPTIONS` (argv flags do NOT reach Next's forked build workers; the env var does). All npm scripts route through it. If a build still OOMs, close other apps — it needs roughly 2 GB free.

### Operational Quick Reference
```bash
python verify_live_llm.py --tasks --max-tokens 400   # prove the model, tally tokens
python clean_db.py                                    # PASTE matrix -> cold
python clean_db.py --delete                           # remove paste.db (stop backend first)
cd backend && .venv/Scripts/python -m pytest tests -q  # 169 tests
cd frontend && npx tsc --noEmit                        # typecheck both routes
cd frontend && npm run build                          # routes through the semi-space wrapper
```
