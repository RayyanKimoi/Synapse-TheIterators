# SYNAPSE Project Status & Claude Update Log

## Current Status: V3 compiler passes COMPLETE — live LLM integrated, one blocker open
**Date:** October 2026
**Overall Progress:** All four V3 passes are implemented as real code. Every mock
multiplier and fabricated payload is gone from the execution path. The compiler
has been run end-to-end against a real tunneled model. **Open blocker:** the
reference workflow cannot complete a live run until a real `TAVILY_API_KEY` is
supplied — see *Known Gaps*. 118 backend tests pass; Next.js build clean.

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
1. **BLOCKER — no Tavily credential.** `tool_io` nodes now make a real call and fail loudly on the placeholder key, so a live run halts at the three crawlers and the contract correctly reports `halted=True, invariance=None`. Set a real `TAVILY_API_KEY` in `.env`, or run with `LLM_OFFLINE_MODE=true` to simulate tools.
2. **The arena numbers above will change once tools are real.** The 8.5 s tool latency is simulated; real Tavily is ~1–2 s. Expect baseline to fall from ~35 s to roughly 12–15 s, the PASTE overlap to shrink, and the "35 s → 14.7 s / 57.9%" headline to be replaced. **Budget time to re-measure before presenting.**
3. **SLA margin is +270 ms (1.8%).** Observed run-to-run noise is ~20 ms so it should hold, but a slower machine adds real per-node embedding cost on top. Recommendation: raise `max_acceptable_latency_ms` from 15 000 to 20 000 in `deep_research.json` — not changed, it is a stated SLA.
4. **The reference workflow has no fusable pair.** It is LLM → tools → LLM, so Phase 6d claims no gain on it; fusion is proven on purpose-built chains in `test_phase4_fusion.py`. Splitting the synthesizer into two adjacent agents would make fusion visible in the demo but would *not* improve the SLA margin (a fused pair costs `max()` of its members).
5. **Compiled latency is no longer deterministic.** PASTE reports measured race timing, so the determinism test now covers baseline latency and compiled *spend*; the compiled clock moves by a few hundred ms per run.
6. **UI not re-verified in a browser** since the V3 passes landed. The `speculative_prefetch` card is verified by payload shape and typecheck only.
7. **Anatomy explainer modal (not built):** PRD 9.1 calls for an isometric compiler breakdown in the top bar via the `anatomy` skill. The skill is installed; the modal is not wired.
8. **Still simulated, deliberately:** `profile.py`'s hash-seeded latency/token model. It no longer sits in the execution path — it feeds only the planner's *projections* (`baseline_estimate` / `compiled_estimate`), the pre-call budget reservation, and the cost fallback for a self-hosted model litellm cannot price.
9. **`llm_offline_mode` is now a misnomer** — it governs tools too. Renaming touches `.env`, config, README and tests, so it was left alone.

### Observability (PRD Phase 4) — NOT STARTED
OpenTelemetry spans around the FastAPI endpoints and node executions, and the
Langfuse pipe, are not implemented. `opentelemetry-api`, `opentelemetry-sdk`
and `langfuse` are not in `requirements.txt`.

### Environment Note (Windows + Node 24)
Next 14 crashes with `FATAL ERROR: Committing semi space failed` on Node 24, especially under memory pressure. `frontend/scripts/run-next.mjs` wraps the Next CLI and injects `--max-semi-space-size=16` via `NODE_OPTIONS` (argv flags do NOT reach Next's forked build workers; the env var does). All npm scripts route through it. If a build still OOMs, close other apps — it needs roughly 2 GB free.

### Operational Quick Reference
```bash
python verify_live_llm.py --tasks --max-tokens 400   # prove the model, tally tokens
python clean_db.py                                    # PASTE matrix -> cold
python clean_db.py --delete                           # remove paste.db (stop backend first)
cd backend && .venv/Scripts/python -m pytest tests -q  # 118 tests
cd frontend && npm run build                          # routes through the semi-space wrapper
```
