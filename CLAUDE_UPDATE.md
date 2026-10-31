# SYNAPSE Project Status & Claude Update Log

## Current Status: Phase 3 (Backend V2 Refactor COMPLETE)
**Date:** October 2026
**Overall Progress:** Project has pivoted to the V3 Master PRD (Ready-Node Scheduler, PASTE, DSPy). The V2 Ready-Node refactor has landed and is verified. Frontend remains functionally wired but visually rejected.

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

### Immediate Next Steps (Strict Order)
1. ~~**Backend Refactor:** Ready-Node scheduler replacing topological depth-tiering.~~ **DONE — see Phase 3a above.**
2. **UI Overhaul (NOW ACTIVE):** Radically redesign the frontend to match the dark-mode liquid-chrome DevEx — Deep Slate `#08090C`, Card Surfaces `#12141A`, Electric Cyan / Neon Emerald / Deep Violet / Crimson node states, Componentry `pixel-canvas` + `liquid-chrome` accents, `flight-status-card` Agent Profile Cards, and the GSAP Optimization Matchmaker swipe deck (which does not exist yet).
3. **Remaining V3 passes (not started):** real Context-Aware semantic cache (Redis + sentence-transformers, 0.85–0.90 band + model/prompt-hash/tool-param guardrails), PASTE SQLite transition matrix at 0.75 confidence, and the DSPy fusion analyzer. Note: the IR has no `side_effect` field yet, so fusion cannot currently honour the PRD's hard exclusion of side-effecting tools — that field must be added first.

### Known Copy Drift (cosmetic, fix during UI overhaul)
`TopNav.tsx` and `RaceArena.tsx` still render the phrase "N topological tiers · depth N". The underlying value is now layout metadata, not an execution partition, so the wording should change to reflect Ready-Node dispatch.
