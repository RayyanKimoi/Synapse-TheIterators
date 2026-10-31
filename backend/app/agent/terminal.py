"""The agent terminal: commands or plain English, planned into steps that run
against the real compiler, runtime and cache.

Planning is deterministic on purpose. The terminal has to work on a machine
with no model behind the gateway -- the same offline path the arena already
supports -- so intent is read from a fixed vocabulary instead of being asked of
an LLM. Every step then calls the code the HTTP API calls: `compile` is the real
planner, `run` and `race` are real executions through `stream_telemetry`, and
`cache` reads the live semantic cache.

Events are plain dicts, streamed to the browser as SSE:
  plan  -- the steps about to run
  step  -- one step starting
  line  -- one line of output, with a tone the UI colours
  ui    -- an instruction for the dashboard (select a workflow)
  done  -- the request finished, ok or not
"""

import asyncio
import difflib
import re
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from .. import registry
from ..compiler.dag import CompileError
from ..compiler.planner import CompilePlan, compile_workflow
from ..config import get_settings
from ..llm import lsh
from ..llm.cache import get_cache
from ..llm.gateway import LLMGateway
from ..llm.judge import GeminiJudge, is_simulated
from ..models.ir import WorkflowIR
from ..models.telemetry import NodeStatus, PipelineType, RunSummary, TelemetryFrame
from ..runtime.paste import get_matrix
from ..runtime.runner import stream_telemetry

Event = dict[str, Any]

# Offline rehearsal replays simulated latency this much faster; reported numbers
# are unchanged. With live models the runner forces real time regardless.
RUN_TIME_SCALE = 20.0

COMMANDS = (
    "help", "health", "workflows", "inspect", "compile", "passes",
    "run", "race", "judge", "cache", "explain", "select",
)

# The last race per workflow, so "race it, then judge it" judges that race
# instead of running a second one. Process memory, like the semantic cache.
_LAST_RACE: dict[str, tuple[RunSummary, RunSummary, "Step"]] = {}

# --- plain-English vocabulary --------------------------------------------------

_VERBS: tuple[tuple[str, str], ...] = (
    ("help", r"\bhelp\b|\bcommands\b|what can you do|\busage\b|^\?$"),
    ("health", r"\bhealth\b|\bstatus\b|\bping\b|\bdiagnos\w*"),
    ("explain", r"\bexplain\b|\bwhat(?:'s| is| are| does)\b|\bhow (?:does|do|is)\b|\bdefine\b|\bwhy\b"),
    ("race", r"\brace\b|\bcompare\b|\bversus\b|\bvs\b\.?|\bbenchmark\w*|head[- ]to[- ]head|side[- ]by[- ]side|\bboth\b"),
    ("run", r"\brun\b|\bexecute\b|\blaunch\b|\bstart\b"),
    ("judge", r"\bjudge\b|\bverify\b|\bcertify\b|\bequivalen\w*|\bsame (?:answer|output)s?\b|\bcalibrat\w*|\bself-?test\b"),
    # "compiled" is a pipeline mode ("run compiled"), never a request to compile.
    ("compile", r"\bcompil(?:e|ing)\b|\boptimi[sz]e\b|\boptimi[sz]ing\b|\banaly[sz]\w*|\bplan\b|\bschedul\w*|\btiers?\b"),
    ("passes", r"\bpasses\b|\bcandidates?\b|\bsuggestions?\b|\bmatchmaker\b|\boptimi[sz]ations\b"),
    # Not "show": "show workflows" and "show me the passes" mean other tools.
    # A bare "show <workflow>" falls back to inspect in `_tools_in`.
    ("inspect", r"\binspect\b|\bdescribe\b|\bnodes\b|\bdetails?\b|\bstructure\b|\bdag\b|\bgraph\b"),
    ("cache", r"\bcache\b|\blsh\b|\bsimhash\b|\bhamming\b"),
    ("workflows", r"\bworkflows\b|\blist\b|\bavailable\b|\bpipelines\b"),
    ("select", r"\bselect\b|\bswitch to\b|\bfocus on\b|\bopen\b"),
)
_VERB_PATTERNS = tuple((tool, re.compile(pattern, re.I)) for tool, pattern in _VERBS)
_EXPLAIN = dict(_VERB_PATTERNS)["explain"]
_SHOW = re.compile(r"\bshow\b|\bdisplay\b", re.I)

_CLAUSES = re.compile(r"\s*(?:;|&&|\n|\band then\b|\bthen\b|\bafter that\b|\bafterwards\b)\s*", re.I)
_QUOTED = re.compile(r"\"([^\"]+)\"|'([^']+)'")
_BASELINE = re.compile(r"\bbaseline\b|\bserial\b|\bsequential\w*|\bunoptimi[sz]ed\b|\bnaive\b", re.I)
_COMPILED = re.compile(r"\bcompiled\b|\boptimi[sz]ed\b|\bparallel\b", re.I)
_WARM = re.compile(r"\bwarm\b|\bprimed\b|--warm|\bwith (?:a |the )?(?:warm )?cache\b", re.I)
_COLD = re.compile(r"\bcold\b|without (?:a |the )?cache|\bno cache\b", re.I)
_DISABLE = re.compile(
    r"(?:without|no|disable|reject|skip|minus)\s+(?:the\s+)?"
    r"(prompt[ _-]?fusion|fusion|dspy|paste|prefetch\w*|speculat\w*|parallel\w*|dispatch)",
    re.I,
)
_DISABLE_FLAG = re.compile(r"--disable[= ]([\w,.-]+)", re.I)
_CALIBRATE = re.compile(r"\bcalibrat\w*|\bself-?test\b", re.I)
_KIND_OF = {
    "prompt": "prompt_fusion", "fusion": "prompt_fusion", "dspy": "prompt_fusion",
    "paste": "speculative_prefetch", "prefetch": "speculative_prefetch",
    "speculat": "speculative_prefetch", "parallel": "parallelize", "dispatch": "parallelize",
}
_STOPWORDS = {
    "the", "a", "an", "and", "with", "for", "of", "to", "on", "it", "this", "that",
    "me", "my", "please", "can", "you", "workflow", "pipeline", "run", "compile",
}


@dataclass(frozen=True)
class Step:
    tool: str
    workflow_id: str | None = None
    mode: PipelineType = PipelineType.COMPILED
    warm: bool = False
    disable: tuple[str, ...] = ()
    query: str | None = None
    topic: str | None = None
    calibrate: bool = False

    @property
    def title(self) -> str:
        target = f" {self.workflow_id}" if self.workflow_id else ""
        if self.tool == "judge" and self.calibrate:
            return "judge selftest"
        if self.tool == "run":
            extras = [self.mode.value]
            if self.warm:
                extras.append("warm cache")
            extras += [f"without {kind}" for kind in self.disable]
            return f"run{target} ({', '.join(extras)})"
        if self.tool == "race":
            return f"race{target}{' (warm cache)' if self.warm else ''}"
        if self.tool == "explain":
            return f"explain {self.topic or 'synapse'}"
        return f"{self.tool}{target}"

    def describe(self) -> dict[str, Any]:
        return {"tool": self.tool, "title": self.title}


def _tools_in(clause: str) -> list[str]:
    """Tools a clause asks for, in the order its words ask for them."""
    found = sorted(
        (match.start(), tool)
        for tool, pattern in _VERB_PATTERNS
        for match in [pattern.search(clause)]
        if match
    )
    tools: list[str] = []
    for _, tool in found:
        if tool not in tools:
            tools.append(tool)
    if "help" in tools:
        return ["help"]
    if "explain" in tools:
        return ["explain"]  # a question is answered, not executed
    if "race" in tools:
        tools = [t for t in tools if t != "run"]
    if "race" in tools or "run" in tools:
        tools = [t for t in tools if t != "cache"]  # "with a warm cache" is a flag
    if "compile" in tools:
        tools = [t for t in tools if t != "passes"]  # compile already prints them
    if len(tools) > 1:
        # "list" is generic: "list the nodes" is an inspect, not a listing.
        tools = [t for t in tools if t != "workflows"]
    if "run" in tools and _BASELINE.search(clause) and _COMPILED.search(clause):
        tools = ["race" if t == "run" else t for t in tools]
    if "judge" in tools:
        tools = [t for t in tools if t != "run"]  # a judge needs a race, not one run
    if "judge" in tools and "race" in tools:
        # "judge the race" names the judge first, but the race has to exist first.
        tools = [t for t in tools if t != "judge"] + ["judge"]
    if not tools and _SHOW.search(clause):
        tools = ["inspect"]
    return tools


def _kind(word: str) -> str:
    """A pass kind from its everyday name; anything else is a candidate id."""
    lowered = word.lower()
    return next((kind for key, kind in _KIND_OF.items() if lowered.startswith(key)), word)


def _workflow_in(clause: str, known: list[registry.WorkflowSummary]) -> str | None:
    lowered = clause.lower()
    for summary in known:
        if summary.workflow_id.lower() in lowered:
            return summary.workflow_id
    words = {w for w in re.findall(r"[a-z0-9]+", lowered) if len(w) >= 3} - _STOPWORDS
    best, best_score = None, 0
    for summary in known:
        vocabulary = set(re.findall(r"[a-z0-9]+", f"{summary.workflow_id} {summary.name}".lower()))
        score = len(words & (vocabulary - _STOPWORDS - {"wf", "v1", "v2", "v3"}))
        if score > best_score:
            best, best_score = summary.workflow_id, score
    return best


def plan(text: str, *, workflow_id: str | None = None) -> list[Step]:
    """Read a request into executable steps. Empty when nothing was understood.

    A clause that names no workflow inherits the previous clause's, then the one
    selected in the dashboard, then the first one loaded -- so "compile market,
    then race it" does what it says.
    """
    known = registry.summaries()
    current = workflow_id if any(s.workflow_id == workflow_id for s in known) else None
    current = current or (known[0].workflow_id if known else None)

    steps: list[Step] = []
    for clause in filter(None, (part.strip() for part in _CLAUSES.split(text.strip()))):
        quoted = next((a or b for a, b in _QUOTED.findall(clause)), None)
        bare = _QUOTED.sub(" ", clause)
        tools = _tools_in(bare)
        named = _workflow_in(bare, known)
        if named is None and (explicit := re.search(r"\bwf_\w+", bare)):
            # A typed id that matches nothing must fail loudly, not quietly run
            # against whichever workflow happens to be selected.
            named = explicit.group(0)
        current = named or current

        disable = [_kind(word) for word in _DISABLE.findall(bare)]
        for flag in _DISABLE_FLAG.findall(bare):
            disable += [_kind(item) for item in flag.split(",") if item]
        mode = PipelineType.BASELINE if _BASELINE.search(bare) and not _COMPILED.search(bare) else PipelineType.COMPILED

        for tool in tools:
            topic = None
            if tool == "explain":
                topic = quoted or _EXPLAIN.sub(" ", bare).strip(" ?.!") or None
            steps.append(
                Step(
                    tool=tool,
                    workflow_id=current if tool not in ("help", "health", "explain", "workflows", "cache") else None,
                    mode=mode,
                    warm=bool(_WARM.search(bare)) and not _COLD.search(bare),
                    disable=tuple(dict.fromkeys(disable)),
                    query=quoted if tool in ("run", "race", "judge") else None,
                    topic=topic,
                    calibrate=tool == "judge" and bool(_CALIBRATE.search(bare)),
                )
            )
    return steps


def suggest(text: str) -> list[str]:
    first = (text.strip().split() or [""])[0].lower()
    return difflib.get_close_matches(first, COMMANDS, n=3, cutoff=0.5)


# --- output helpers ------------------------------------------------------------


def _line(text: str, tone: str = "text") -> Event:
    return {"type": "line", "text": text, "tone": tone}


def _ms(value: float) -> str:
    return f"{round(value):,} ms"


def _workflow(step: Step) -> WorkflowIR:
    found = registry.get(step.workflow_id or "")
    if found is None:
        raise LookupError(f"no workflow '{step.workflow_id}' -- try `workflows`")
    return found


async def _compile(workflow: WorkflowIR) -> CompilePlan:
    try:
        return compile_workflow(workflow, await get_matrix().snapshot())
    except CompileError as exc:
        raise ValueError(f"compile rejected the graph: {exc.message}") from exc


# --- tools -------------------------------------------------------------------------


async def _help(_: Step, __: "Context") -> AsyncIterator[Event]:
    yield _line("commands", "accent")
    rows = [
        ("workflows", "list the workflows the compiler has loaded"),
        ("inspect [wf]", "the IR: every node, its type, persona and dependencies"),
        ("compile [wf]", "build the DAG, tier it, and estimate both pipelines"),
        ("passes [wf]", "the optimization passes the compiler proposes"),
        ("run [wf] [baseline|compiled] [--warm] [--disable kind]", "execute one pipeline for real"),
        ("race [wf] [--warm]", "baseline and compiled concurrently, with the speedup"),
        ("judge [wf]", "Gemini checks the last race's two answers say the same thing"),
        ("judge selftest", "calibrate the judge on pairs whose answer is known"),
        ("cache", "semantic-cache backend, threshold and SimHash prefilter"),
        ("health", "backend, model gateway and cache status"),
        ("explain <topic>", "parallelize, fusion, paste, cache, lsh, contract, breaker"),
        ("select <wf>", "point the dashboard at a workflow"),
        ("arena race|baseline|compiled", "replay it live in the arena (runs in the UI)"),
        ("clear", "clear the screen  ·  ↑/↓ history  ·  Tab completes  ·  Ctrl+C stops"),
    ]
    width = max(len(name) for name, _ in rows)
    for name, description in rows:
        yield _line(f"  {name.ljust(width)}  {description}", "muted")
    yield _line("plain English works too", "accent")
    for example in (
        "compile the market workflow and show me the passes",
        "race it, then judge it",
        "run baseline then run compiled without fusion",
        "what is paste?",
    ):
        yield _line(f"  › {example}", "muted")


async def _health(_: Step, __: "Context") -> AsyncIterator[Event]:
    settings = get_settings()
    probe = await LLMGateway(settings).probe()
    stats = await get_cache().stats()
    yield _line(f"backend    ok · environment {settings.environment}", "ok")
    offline = "offline rehearsal" if settings.llm_offline_mode else "live mode"
    gateways = ", ".join(f"{name} {'up' if probe.get(name) else 'down'}" for name in ("ollama", "litellm_proxy"))
    yield _line(f"llm        {offline} · {gateways}", "info")
    yield _line(
        f"cache      {stats['backend']} · threshold {stats['threshold']} · "
        f"{stats['entries']} entries in {stats['namespaces']} namespaces",
        "info",
    )
    yield _line(f"workflows  {len(registry.summaries())} loaded", "info")


async def _workflows(_: Step, __: "Context") -> AsyncIterator[Event]:
    known = registry.summaries()
    if not known:
        yield _line("no workflows loaded -- check WORKFLOWS_DIR", "warn")
        return
    width = max(len(s.workflow_id) for s in known)
    for summary in known:
        yield _line(f"  {summary.workflow_id.ljust(width)}  {summary.node_count} nodes  {summary.name}", "text")


async def _inspect(step: Step, context: "Context") -> AsyncIterator[Event]:
    workflow = _workflow(step)
    async for event in context.select(workflow.workflow_id):
        yield event
    yield _line(f"{workflow.name} · budget ${workflow.budget_limit_usd:.2f} · {len(workflow.nodes)} nodes", "accent")
    width = max(len(node.id) for node in workflow.nodes)
    for node in workflow.nodes:
        kind = node.type.value if hasattr(node.type, "value") else str(node.type)
        deps = ", ".join(node.dependencies) or "—"
        flag = "  [side effect]" if node.side_effect else ""
        yield _line(f"  {node.id.ljust(width)}  {kind:<9} ← {deps}{flag}", "text")
        yield _line(f"  {''.ljust(width)}  {node.persona}", "muted")
    assertions = workflow.test_assertions
    yield _line(
        f"contract   keys {', '.join(assertions.required_output_keys) or '—'} · "
        f"similarity ≥ {assertions.min_semantic_similarity} · latency ≤ {_ms(assertions.max_acceptable_latency_ms)}",
        "muted",
    )


async def _compile_tool(step: Step, context: "Context") -> AsyncIterator[Event]:
    workflow = _workflow(step)
    async for event in context.select(workflow.workflow_id):
        yield event
    compiled = await _compile(workflow)
    yield _line(
        f"{compiled.name} · {compiled.node_count} nodes · {compiled.edge_count} edges · depth {compiled.max_depth}",
        "accent",
    )
    for index, tier in enumerate(compiled.execution_tiers):
        parallel = "  ⇉ concurrent" if len(tier) > 1 else ""
        yield _line(f"  tier {index}  {', '.join(tier)}{parallel}", "info" if len(tier) > 1 else "text")
    base, comp = compiled.baseline_estimate, compiled.compiled_estimate
    yield _line(f"  baseline  {_ms(base.latency_ms):>12} · {base.tokens:,} tok · ${base.cost_usd:.5f}", "warn")
    yield _line(f"  compiled  {_ms(comp.latency_ms):>12} · {comp.tokens:,} tok · ${comp.cost_usd:.5f}", "ok")
    yield _line(f"  projected latency cut {compiled.latency_reduction_pct:.1f}%", "ok")
    async for event in _passes_of(compiled):
        yield event
    for warning in compiled.warnings:
        yield _line(f"  ! {warning}", "warn")


async def _passes_of(compiled: CompilePlan) -> AsyncIterator[Event]:
    candidates = compiled.optimization_candidates
    if not candidates:
        yield _line("  no optimization passes apply to this graph", "muted")
        return
    yield _line(f"  passes ({len(candidates)})", "accent")
    for candidate in candidates:
        kind = getattr(candidate.kind, "value", candidate.kind)
        yield _line(
            f"    [{kind}] {candidate.title} · −{candidate.projected_latency_saved_ms / 1000:.1f}s "
            f"· −{candidate.projected_tokens_saved:,} tok · id {candidate.id}",
            "text",
        )


async def _passes(step: Step, context: "Context") -> AsyncIterator[Event]:
    workflow = _workflow(step)
    async for event in context.select(workflow.workflow_id):
        yield event
    async for event in _passes_of(await _compile(workflow)):
        yield event


@dataclass
class _Lane:
    mode: PipelineType
    label: str
    summary: RunSummary | None = None
    seen: dict[str, str] = field(default_factory=dict)


async def _lane_events(lane: _Lane, workflow: WorkflowIR, step: Step, disabled: frozenset[str]) -> AsyncIterator[Event]:
    settings = get_settings()
    stream = stream_telemetry(
        workflow,
        mode=lane.mode,
        cache_warm=step.warm,
        tick_ms=settings.telemetry_tick_ms,
        time_scale=RUN_TIME_SCALE,
        query=step.query,
        disabled=disabled,
    )
    prefix = f"{lane.label:<8} " if lane.label else ""
    async for message in stream:
        if message["event"] == "run_complete":
            lane.summary = RunSummary.model_validate_json(message["data"])
            continue
        frame = TelemetryFrame.model_validate_json(message["data"])
        for node_id, state in frame.node_states.items():
            status = state.status.value if isinstance(state.status, NodeStatus) else str(state.status)
            if lane.seen.get(node_id) == status:
                continue
            lane.seen[node_id] = status
            if status == NodeStatus.RUNNING.value:
                yield _line(f"  {prefix}▸ {node_id} dispatched", "muted")
            elif status == NodeStatus.CACHED.value:
                yield _line(f"  {prefix}◆ {node_id} served from cache · {_ms(state.latency_ms)} · 0 tok", "ok")
            elif status == NodeStatus.COMPLETED.value:
                yield _line(f"  {prefix}✓ {node_id} {_ms(state.latency_ms)} · {state.tokens_consumed:,} tok", "info")
            elif status == NodeStatus.FAILED.value:
                yield _line(f"  {prefix}✗ {node_id} {state.error or 'failed'}", "error")


_FINISHED = object()


async def _drive(lanes: list[_Lane], workflow: WorkflowIR, step: Step, disabled: frozenset[str]) -> AsyncIterator[Event]:
    """Run every lane concurrently and interleave their output as it happens."""
    queue: asyncio.Queue[Any] = asyncio.Queue()

    async def worker(lane: _Lane) -> None:
        try:
            async for event in _lane_events(lane, workflow, step, disabled):
                await queue.put(event)
        finally:
            await queue.put(_FINISHED)

    tasks = [asyncio.create_task(worker(lane)) for lane in lanes]
    try:
        finished = 0
        while finished < len(tasks):
            item = await queue.get()
            if item is _FINISHED:
                finished += 1
            else:
                yield item
    finally:
        # The browser hung up mid-run: stop the executions instead of leaking them.
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    for task in tasks:
        if not task.cancelled() and task.exception():
            raise task.exception()  # type: ignore[misc]


async def _disabled_ids(workflow: WorkflowIR, wanted: tuple[str, ...]) -> tuple[frozenset[str], list[Event]]:
    if not wanted:
        return frozenset(), []
    candidates = (await _compile(workflow)).optimization_candidates
    ids: set[str] = set()
    notes: list[Event] = []
    for item in wanted:
        matched = [c for c in candidates if c.id == item or getattr(c.kind, "value", c.kind) == item]
        if matched:
            ids.update(c.id for c in matched)
            notes.append(_line(f"  rejecting {item} → {', '.join(c.id for c in matched)}", "warn"))
        else:
            notes.append(_line(f"  no {item} pass on this graph; nothing to reject", "muted"))
    return frozenset(ids), notes


def _mode_note() -> Event:
    if get_settings().llm_offline_mode:
        return _line(f"  offline rehearsal · replayed ×{RUN_TIME_SCALE:g}, reported latencies unchanged", "muted")
    return _line("  live mode · real time (set LLM_OFFLINE_MODE=true to rehearse faster)", "muted")


def _summary_lines(summary: RunSummary, label: str) -> list[Event]:
    metrics, contract = summary.aggregate_metrics, summary.contract
    verdict = "PASSED" if contract.passed else "FAILED"
    lines = [
        _line(
            f"  {label} {_ms(summary.total_elapsed_ms)} · {summary.cache_hits}/{summary.node_count} cache hits · "
            f"{metrics.total_tokens:,} tok · ${metrics.total_cost_usd:.5f}",
            "accent",
        ),
        _line(
            f"  contract {verdict} · latency {_ms(contract.latency_ms)} / {_ms(contract.max_acceptable_latency_ms)} · "
            f"invariance {contract.semantic_invariance if contract.semantic_invariance is not None else '—'}",
            "ok" if contract.passed else "error",
        ),
    ]
    if contract.missing_output_keys:
        lines.append(_line(f"  missing output keys: {', '.join(contract.missing_output_keys)}", "error"))
    return lines


async def _run(step: Step, context: "Context") -> AsyncIterator[Event]:
    workflow = _workflow(step)
    async for event in context.select(workflow.workflow_id):
        yield event
    disabled, notes = await _disabled_ids(workflow, step.disable)
    for note in notes:
        yield note
    yield _mode_note()
    lane = _Lane(step.mode, "")
    async for event in _drive([lane], workflow, step, disabled):
        yield event
    if lane.summary is None:
        raise RuntimeError("the run ended without a summary")
    for event in _summary_lines(lane.summary, lane.mode.value):
        yield event


async def _race(step: Step, context: "Context") -> AsyncIterator[Event]:
    workflow = _workflow(step)
    async for event in context.select(workflow.workflow_id):
        yield event
    disabled, notes = await _disabled_ids(workflow, step.disable)
    for note in notes:
        yield note
    yield _mode_note()
    baseline = _Lane(PipelineType.BASELINE, "baseline")
    compiled = _Lane(PipelineType.COMPILED, "compiled")
    async for event in _drive([baseline, compiled], workflow, step, disabled):
        yield event
    if baseline.summary is None or compiled.summary is None:
        raise RuntimeError("a lane ended without a summary")
    _LAST_RACE[workflow.workflow_id] = (baseline.summary, compiled.summary, step)
    for lane in (baseline, compiled):
        for event in _summary_lines(lane.summary, f"{lane.label:<8}"):  # type: ignore[arg-type]
            yield event
    slow, fast = baseline.summary.total_elapsed_ms, compiled.summary.total_elapsed_ms
    if fast > 0:
        saved = slow - fast
        yield _line(
            f"  compiled is {slow / fast:.2f}× faster · {_ms(saved)} saved ({saved / slow * 100:.1f}%)",
            "ok" if saved > 0 else "warn",
        )
    yield _line("  tip: `arena race` replays this live · `judge` checks both gave the same answer", "muted")


async def _judge(step: Step, context: "Context") -> AsyncIterator[Event]:
    judge = GeminiJudge()
    if not judge.available:
        yield _line("judge not configured -- add GEMINI_API_KEY to the repo-root .env", "warn")
        return

    if step.calibrate:
        yield _line(f"calibrating {judge.model} on two pairs whose answer is known…", "muted")
        results = await judge.calibrate()
        for result in results:
            verdict = result.verdict
            said = "equivalent" if verdict.equivalent else "different"
            wanted = "equivalent" if result.expected_equivalent else "different"
            yield _line(
                f"  {'✓' if result.correct else '✗'} {result.case}: expected {wanted}, judged {said} · "
                f"{verdict.score}/5 · {_ms(verdict.latency_ms)}",
                "ok" if result.correct else "error",
            )
            for item in verdict.discrepancies:
                yield _line(f"      - {item}", "muted")
        if all(result.correct for result in results):
            yield _line("  judge calibrated: it tells a faithful paraphrase from a changed figure", "ok")
        else:
            yield _line("  judge FAILED calibration: do not rely on its verdicts", "error")
        return

    workflow = _workflow(step)
    async for event in context.select(workflow.workflow_id):
        yield event
    if workflow.workflow_id not in _LAST_RACE:
        yield _line("no race to judge yet -- racing first", "muted")
        async for event in _race(step, context):
            yield event
    baseline, compiled, raced = _LAST_RACE[workflow.workflow_id]

    if is_simulated(baseline) or is_simulated(compiled):
        yield _line(
            "judge skipped: these outputs are offline stubs ([synapse:mock]); a verdict on placeholders means nothing",
            "warn",
        )
        yield _line("  run the backend with a live model to judge real outputs · `judge selftest` checks the judge", "muted")
        return

    yield _line(f"judging with {judge.model}: dropped facts and added facts, both at once…", "muted")
    verdict = await judge.compare(
        baseline.final_output,
        compiled.final_output,
        query=raced.query or workflow.name,
        required_keys=workflow.test_assertions.required_output_keys,
    )
    yield _line(
        f"  {'✓ EQUIVALENT' if verdict.equivalent else '✗ NOT EQUIVALENT'} · {verdict.score}/5 · "
        f"{verdict.model} · {_ms(verdict.latency_ms)} · {verdict.tokens:,} judge tok",
        "ok" if verdict.equivalent else "error",
    )
    for item in verdict.discrepancies:
        yield _line(f"      - {item}", "warn")
    if verdict.equivalent and not verdict.discrepancies:
        yield _line(f"  {verdict.dropped.rationale}", "muted")


async def _cache(_: Step, __: "Context") -> AsyncIterator[Event]:
    stats = await get_cache().stats()
    yield _line(f"backend     {stats['backend']}", "info")
    yield _line(f"threshold   cosine ≥ {stats['threshold']} on query and context, each", "info")
    yield _line(
        f"prefilter   {stats['signature_bits']}-bit SimHash · Hamming ≤ {stats['hamming_cutoff']} "
        f"(≈ cosine ≥ {lsh.estimated_cosine(int(stats['hamming_cutoff'])):.2f}, 5σ margin)",
        "info",
    )
    yield _line(f"entries     {stats['entries']} in {stats['namespaces']} namespaces", "info")


_TOPICS: dict[str, tuple[str, ...]] = {
    "synapse": (
        "SYNAPSE compiles an agent workflow the way a compiler treats a program: parse the JSON IR,",
        "prove which nodes are independent, restructure the graph, then execute it with telemetry.",
    ),
    "parallelize": (
        "Ready-Node dispatch: an asyncio queue tracks each node's unresolved dependencies and fires",
        "the node the moment the count reaches zero, so independent agents run concurrently.",
    ),
    "fusion": (
        "DSPy prompt fusion merges compatible neighbouring prompts into one generation and splits",
        "the response back by schema -- one round trip instead of two. Side-effect nodes never fuse.",
    ),
    "paste": (
        "PASTE speculative prefetch learns tool-call transitions and warms the next likely tool",
        "while the upstream agent is still generating, hiding the tool's latency behind it.",
    ),
    "cache": (
        "The context-aware semantic cache embeds query and upstream context separately; both must",
        "clear the threshold for the same node, model and prompt before an answer is reused.",
    ),
    "lsh": (
        "Each cached vector carries a 256-bit SimHash. A probe compares signatures first (XOR +",
        "popcount) and only computes the exact cosine for entries that could clear the threshold.",
    ),
    "contract": (
        "Every run is checked against the IR's test assertions: required output keys present,",
        "semantic invariance above the floor, and latency within the SLA.",
    ),
    "breaker": (
        "The gateway tracks spend against the workflow's budget and trips a circuit breaker",
        "before a run can overshoot it.",
    ),
    "judge": (
        "An independent model (Gemini) compares the baseline and compiled answers both ways:",
        "what the compiled run dropped or changed, and what it added. Equivalent only if both pass.",
    ),
}
_TOPIC_WORDS = {
    "parallel": "parallelize", "dispatch": "parallelize", "concurren": "parallelize", "faster": "parallelize",
    "fusion": "fusion", "fuse": "fusion", "dspy": "fusion",
    "paste": "paste", "prefetch": "paste", "speculat": "paste",
    "lsh": "lsh", "simhash": "lsh", "hamming": "lsh", "hash": "lsh",
    "cache": "cache", "semantic": "cache", "embedding": "cache",
    "contract": "contract", "assert": "contract", "invarian": "contract", "sla": "contract",
    "breaker": "breaker", "budget": "breaker", "cost": "breaker",
    "judge": "judge", "gemini": "judge", "equivalen": "judge", "verif": "judge",
}


async def _explain(step: Step, _: "Context") -> AsyncIterator[Event]:
    words = (step.topic or "").lower()
    topic = next((name for key, name in _TOPIC_WORDS.items() if key in words), "synapse")
    yield _line(topic, "accent")
    for text in _TOPICS[topic]:
        yield _line(f"  {text}", "text")


async def _select(step: Step, context: "Context") -> AsyncIterator[Event]:
    workflow = _workflow(step)
    async for event in context.select(workflow.workflow_id, force=True):
        yield event
    yield _line(f"dashboard now on {workflow.workflow_id} · {workflow.name}", "ok")


_TOOLS: dict[str, Callable[[Step, "Context"], AsyncIterator[Event]]] = {
    "help": _help,
    "health": _health,
    "workflows": _workflows,
    "inspect": _inspect,
    "compile": _compile_tool,
    "passes": _passes,
    "run": _run,
    "race": _race,
    "judge": _judge,
    "cache": _cache,
    "explain": _explain,
    "select": _select,
}


@dataclass
class Context:
    """What the dashboard is pointed at, so the agent only re-points it on change."""

    workflow_id: str | None

    async def select(self, workflow_id: str, *, force: bool = False) -> AsyncIterator[Event]:
        if force or workflow_id != self.workflow_id:
            self.workflow_id = workflow_id
            yield {"type": "ui", "action": "select", "workflow_id": workflow_id}


async def run_agent(text: str, *, workflow_id: str | None = None) -> AsyncIterator[Event]:
    """Plan `text`, then execute each step, streaming every event as it happens."""
    started = time.perf_counter()
    steps = plan(text, workflow_id=workflow_id)
    if not steps:
        hint = suggest(text)
        yield _line(f"didn't understand “{text.strip()}”", "warn")
        yield _line(f"  did you mean: {', '.join(hint)}?" if hint else "  type `help` for what I can do", "muted")
        yield {"type": "done", "ok": False, "elapsed_ms": 0}
        return

    yield {"type": "plan", "steps": [step.describe() for step in steps]}
    context = Context(workflow_id)
    ok = True
    for index, step in enumerate(steps):
        yield {"type": "step", "index": index, "title": step.title}
        try:
            async for event in _TOOLS[step.tool](step, context):
                yield event
        except Exception as exc:  # one failed step stops the plan, not the server
            ok = False
            yield _line(f"✗ {step.title}: {exc}", "error")
            break
    yield {"type": "done", "ok": ok, "elapsed_ms": int((time.perf_counter() - started) * 1000)}


__all__ = ["Step", "plan", "run_agent", "suggest"]
