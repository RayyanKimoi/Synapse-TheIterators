# SYNAPSE Backend — Phase 1

Compiler front end, DAG scheduler and telemetry stream for the SYNAPSE workflow
runtime. Implements PRD Phase 1 (Foundation, Schemas & Telemetry Stream).

## Setup

```bash
cd backend
python -m venv .venv                      # Python 3.11+
.venv/Scripts/activate                    # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example ../.env                # optional; defaults work offline
uvicorn app.main:app --reload --port 8000
```

Interactive API docs: <http://localhost:8000/docs>

```bash
pytest -q                                 # 43 checks (Phase 1 + V3 runtime wiring)
```

## Endpoints

| Method | Path | Purpose |
| :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Status plus LiteLLM/Ollama reachability for the offline badge. |
| `GET` | `/api/v1/workflows` | Workflow selector feed. |
| `GET` | `/api/v1/workflows/{id}` | Full IR document. |
| `POST` | `/api/v1/compile` | Validate IR, reject cycles, return the tiered plan. |
| `POST` | `/api/v1/execute/stream` | SSE telemetry; body selects workflow and mode. |
| `GET` | `/api/v1/execute/stream` | Same stream for the browser's native `EventSource`. |

Stream parameters: `mode=compiled|baseline`, `cache_warm=true|false`,
`time_scale=1..200` (compresses simulated latency for rehearsal without altering
reported latencies; forced to 1 when live models are in the loop), and
`query=...` (the user request the root agents work on; defaults to the workflow
name).

The final `telemetry_update` frame and `run_complete` carry a `contract` verdict
against the IR's `test_assertions`; `run_complete` also carries `final_output`
and `llm_calls` (completed calls by where they were served: `mock`, `ollama`,
`litellm_proxy`).

```bash
curl -s localhost:8000/api/v1/compile -H 'content-type: application/json' \
  -d @../workflows/deep_research.json | python -m json.tool

curl -N 'localhost:8000/api/v1/execute/stream?workflow_id=wf_deep_research_v1&mode=compiled'
```

## Layout

```
app/
  main.py                FastAPI app factory + CORS
  config.py              .env-backed settings (PRD 10.3)
  registry.py            loads workflows/*.json
  api/routes.py          HTTP + SSE surface
  models/ir.py           Pydantic v2 JSON IR (PRD 5.2)
  models/telemetry.py    SSE event contract (PRD 8.1/8.2)
  compiler/dag.py        NetworkX graph, cycle check, depth (canvas layout only)
  compiler/scheduler.py  Ready-Node scheduler: asyncio.Queue + TaskGroup, branch halting
  compiler/planner.py    CompilePlan + optimization candidates
  runtime/profile.py     deterministic latency model for simulated work
  runtime/executor.py    per-node work: LLM nodes via the gateway, tool stubs
  runtime/contract.py    post-run test_assertions verdict
  runtime/runner.py      SSE frame generator driving the scheduler
  llm/gateway.py         LiteLLM wrapper, Ollama routing, mock fallback,
                         reservation budget + circuit breaker, guardrails
```

## Measured on the reference workflow

`workflows/deep_research.json` (1 extractor -> 3 crawlers -> 1 synthesizer),
offline mode:

| Run | Latency | Tokens | Cost | Contract |
| :--- | ---: | ---: | ---: | :--- |
| Baseline sequential | 35,043 ms | 1,306 | $0.002612 | FAIL (latency > 15,000 ms) |
| Compiled | 8,796 ms | 1,306 | $0.002612 | PASS |
| Compiled, warm cache | 358 ms | 710 | $0.001420 | FAIL (invariance not certifiable) |

Tokens and cost come from the gateway per LLM call, so baseline and compiled
match: compilation changes dispatch, not prompts. Latency is still the
simulated profile, including the not-yet-real prefetch and fusion multipliers.

## What is real and what is still simulated

Real: IR validation, cycle rejection, the Ready-Node scheduler, the SSE stream,
gateway routing for every LLM node, the reservation budget and circuit breaker
(a trip fails the node and halts its descendants), and the post-run contract
check (required output keys, latency).

Still simulated, with the seams in place:

* **Latency without a live model.** In offline mode (or when a live call falls
  back to the mock) node latency comes from the hash-seeded profile in
  `runtime/profile.py`, including the speculative pre-fetch (0.18) and prompt
  fusion (0.55) multipliers, so the race is byte-identical on stage.
* **Cache hits are scheduled, not computed.** `cache_warm=true` marks every
  non-terminal node as a 4 ms hit. The semantic-cache phase swaps that for
  embedding cosine matching at `semantic_cache_similarity_threshold` (0.88),
  which the contract's admission check already reads.
* **Semantic invariance is a structural placeholder.** `correctness_score` is
  1.0 when every node executed its own declared prompt, and 0 (not certifiable)
  when the run halted or a cache substituted an output. Embedding cosine against
  a baseline output replaces it, gated at the IR's `min_semantic_similarity`
  (0.95).
* **Tool nodes are stubs.** No Tavily client is wired; they return a labelled
  `offline_stub` record.
