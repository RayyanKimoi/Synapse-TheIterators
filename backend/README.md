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
pytest -q                                 # 19 Phase 1 acceptance checks
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
`time_scale=1..200` (compresses wall-clock time for rehearsal without altering
reported latencies).

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
  compiler/dag.py        NetworkX graph, cycle check, topological depth, tiers
  compiler/planner.py    CompilePlan + optimization candidates
  runtime/profile.py     deterministic latency/token/cost model + scheduler
  runtime/mock_runner.py SSE frame generator
  llm/gateway.py         LiteLLM wrapper, Ollama routing, mock fallback, budget
```

## Measured on the reference workflow

`workflows/deep_research.json` compiles to 3 tiers (1 / 3 / 1 nodes):

| Run | Latency | Tokens | Cost |
| :--- | ---: | ---: | ---: |
| Baseline sequential | 35,043 ms | 994 | $0.001988 |
| Compiled (parallel + fusion) | 8,796 ms | 751 | $0.001502 |
| Compiled, warm cache | 358 ms | 296 | $0.000592 |

That is a 74.9% latency reduction from compilation and 99.0% with a warm
semantic cache.

## Phase 1 boundaries

Deliberately deferred, with the seams already in place:

* **`runtime/profile.py` is a simulation.** Node latencies, token counts and the
  gains credited to speculative pre-fetch and prompt fusion come from a
  hash-seeded profile, so every run is byte-identical. Phase 3 replaces
  `build_compiled_schedule` with the real `asyncio.gather` engine behind the
  same event contract, which is what lets Phase 2's frontend be built now.
* **Cache hits are scheduled, not computed.** `cache_warm=true` marks every
  non-terminal node as a 4 ms hit. Phase 4 swaps that for Redis plus `fastembed`
  cosine matching at the 0.88 threshold already present in settings.
* **`correctness_score` is a constant** (0.982 compiled, 1.0 baseline). Phase 6
  replaces it with measured semantic-invariance scoring.
* **`LLMGateway` is wired but unused by the runner.** It routes and prices real
  calls today; the Phase 3 engine is what will call it per node.
