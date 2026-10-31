# SYNAPSE Project Status & Claude Update Log

## Current Status: Phase 5 (DevEx Gamification COMPLETE)
**Date:** October 2026
**Overall Progress:** Project has pivoted to the V3 Master PRD (Ready-Node Scheduler, PASTE, DSPy). The V2 Ready-Node refactor landed and is verified. The UI overhaul has landed and is verified in a real browser — the previous visual rejection is resolved.

### Completed & Locked Milestones
* **Phase 1 (Legacy):** Backend scaffolded. SSE telemetry and IR schemas are locked and stable.
* **Phase 2 (Functionality):** Next.js scaffolded. React Flow and Zustand are successfully consuming the SSE stream. GSAP counters are functioning.
* **Skill Governance:** Banned skills removed (`taste-skill`, `gsd-core`, `graphify` — including graphify's `PreToolUse` hooks and its `CLAUDE.md` rule injections). `anatomy`, `ponytail`, `ui-ux-pro-max`, `ui-styling`, and `archify` are active.
* **Phase 3a — V2 Ready-Node Scheduler (VERIFIED):**
  * `compiler/scheduler.py` added: `asyncio.Queue` + `asyncio.TaskGroup` worker pool bounded by `max_concurrent_tasks`. Nodes carry an `in_degree` countdown; on completion children are decremented and any child hitting zero is dispatched instantly.
  * Depth-tiering demoted to layout only. `dag.execution_tiers` renamed `dag.layout_tiers`; `topological_depths` is now explicitly a canvas-column label and never gates dispatch.
  * `runtime/profile.py` tier-barrier cursor (`cursor = max(tier ends)`) deleted. Node placement now comes from `scheduler.ready_node_timings` (start = max of own parents' ends).
  * `runtime/mock_runner.py` SSE stream is now driven by the live scheduler, not a replayed schedule. Baseline runs the same engine over a chain graph, so the arena race compares two dispatch topologies rather than two formulas.
  * `max_concurrent_tasks` is no longer dead config; `CompilePlan` now exposes `node_in_degrees` and `max_concurrency`.
  * **Verification:** 19/19 Phase 1 tests pass. On an asymmetric DAG, ready-node dispatches a node 8000 ms earlier than depth-tiering. Live pool shows real concurrency (peak in-flight > 1). Against `deep_research.json`: baseline 35043 ms, compiled 8796 ms, warm-cache 358 ms with 4 cache hits; at `time_scale=1.0` the stream emits 83 frames with 3 crawler nodes RUNNING simultaneously.
  * **SSE contract unchanged** — `TelemetryFrame` / `RunSummary` field names and the `IDLE/RUNNING/CACHED/COMPLETED/FAILED` vocabulary are untouched, so the frontend does not crash.

* **Phase 5 — UI/UX Overhaul (VERIFIED IN BROWSER):**
  * Design system rebuilt in `globals.css`: layered radial lighting, grain, animated liquid-chrome sheen, `.surface` elevation, `.ticker` instrument type, WCAG 2.2 focus rings, and edge-flow keyframes. Added `--state-blocking` (orange) for the baseline lane.
  * `CustomEdge.tsx` (new): particles ride the real path geometry via `getPointAtLength` — slow single particle on baseline, steady flow on compiled, 3-particle high-velocity emerald burst on cache hit.
  * `MatchmakerDeck.tsx` (new): the "Tinder for optimizations" deck. Pointer-event drag + GSAP (no plugin dependency), elastic snap-back, approve/reject buttons so the gesture is keyboard-reachable. Auto-collapses to a pill when a run starts and stays collapsed, so it never covers the arena.
  * `AgentNode`, `AgentProfileCard`, `AgentRoster`, `RaceArena`, `TopNav`, `Scoreboard` restyled: gradient avatar rings, telemetry ribbons, blocking-stripe indicator, lightning HIT badges, `00:00.000` DOM-direct GSAP stopwatches, trust badges.
  * **Copy drift fixed:** "N topological tiers" is gone from `TopNav.tsx` and `RaceArena.tsx`, replaced with Ready-Node / dependency-graph phrasing.
  * **Verification:** typecheck clean, production build clean, zero console/page errors. Browser-verified: baseline shows 1 orange blocking node while compiled fires 3 cyan crawlers concurrently; race ends 00:35.043 vs 00:08.796; warm-cache finale hits 00:00.358 at 99.0% latency saved with 4/5 cache recall.

### Immediate Next Steps (Strict Order)
1. ~~**Backend Refactor:** Ready-Node scheduler replacing topological depth-tiering.~~ **DONE — Phase 3a.**
2. ~~**UI Overhaul:** dark-mode liquid-chrome DevEx + Matchmaker swipe deck.~~ **DONE — Phase 5.**
3. **Remaining V3 passes (not started):** real Context-Aware semantic cache (Redis + sentence-transformers, 0.85–0.90 band + model/prompt-hash/tool-param guardrails), PASTE SQLite transition matrix at 0.75 confidence, and the DSPy fusion analyzer. Note: the IR has no `side_effect` field yet, so fusion cannot currently honour the PRD's hard exclusion of side-effecting tools — that field must be added first.
4. **Anatomy explainer modal (not built):** PRD 9.1 calls for an isometric compiler breakdown in the top bar via the `anatomy` skill. The skill is installed; the modal is not wired.

### Environment Note (Windows + Node 24)
Next 14 crashes with `FATAL ERROR: Committing semi space failed` on Node 24, especially under memory pressure. `frontend/scripts/run-next.mjs` wraps the Next CLI and injects `--max-semi-space-size=16` via `NODE_OPTIONS` (argv flags do NOT reach Next's forked build workers; the env var does). All npm scripts route through it. If a build still OOMs, close other apps — it needs roughly 2 GB free.
