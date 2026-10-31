"""LLM-as-a-judge, driven through a fake Gemini transport: no network, no key."""

import asyncio
import json

import httpx
import pytest

from app import registry
from app.agent import terminal
from app.agent.terminal import plan, run_agent
from app.config import Settings
from app.llm.judge import GeminiJudge, JudgeError, is_simulated
from app.models.telemetry import AggregateMetrics, ContractReport, PipelineType, RunSummary

WF = registry.summaries()[0].workflow_id
BASELINE = {"summary": "Revenue rose 41% to $18.4B.", "risk_factors": ["export controls"]}
COMPILED = {"summary": "Revenue grew 41 percent to 18.4 billion dollars.", "risk_factors": ["export controls"]}


def _settings(**overrides) -> Settings:
    return Settings(gemini_api_key="test-key", judge_model="gemini-test", **overrides)


def _gemini(verdicts: dict[str, dict], seen: list[dict] | None = None, status: int = 200) -> httpx.MockTransport:
    """Answers each direction by which output the prompt names as REFERENCE."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "test-key"
        assert "key=" not in str(request.url)  # never in the URL
        body = json.loads(request.content)
        if seen is not None:
            seen.append(body)
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "nope"}})
        prompt = body["contents"][0]["parts"][0]["text"]
        reference = prompt.split("REFERENCE:\n", 1)[1].split("\n\nCANDIDATE:", 1)[0]
        direction = "dropped" if "rose 41%" in reference else "added"
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": json.dumps(verdicts[direction])}]}}],
                "usageMetadata": {"totalTokenCount": 100},
            },
        )

    return httpx.MockTransport(handler)


PASS = {"preserved": True, "score": 5, "discrepancies": [], "rationale": "same facts"}


def _compare(transport: httpx.MockTransport, baseline=BASELINE, compiled=COMPILED):
    judge = GeminiJudge(_settings(), transport=transport)
    return asyncio.run(judge.compare(baseline, compiled, query="q", required_keys=["summary"]))


def test_equivalent_only_when_both_directions_pass() -> None:
    seen: list[dict] = []
    verdict = _compare(_gemini({"dropped": PASS, "added": PASS}, seen))
    assert verdict.equivalent and verdict.score == 5 and verdict.discrepancies == []
    assert verdict.tokens == 200 and verdict.model == "gemini-test"
    # Both directions were asked, each with the other output as the reference.
    references = sorted(b["contents"][0]["parts"][0]["text"].split("CANDIDATE:")[0] for b in seen)
    assert len(seen) == 2 and references[0] != references[1]
    assert all(b["generationConfig"]["responseMimeType"] == "application/json" for b in seen)


def test_an_addition_alone_fails_the_verdict() -> None:
    """Kept every baseline fact but invented one: only the reverse direction sees it."""
    added = {"preserved": False, "score": 2, "discrepancies": ["claims a buyback"], "rationale": "x"}
    verdict = _compare(_gemini({"dropped": PASS, "added": added}))
    assert not verdict.equivalent and verdict.score == 2
    assert verdict.discrepancies == ["only in compiled: claims a buyback"]


def test_the_rubric_overrides_a_self_contradicting_verdict() -> None:
    """preserved=true with a score of 3 is not preserved: the rubric says 4+."""
    lenient = {"preserved": True, "score": 3, "discrepancies": ["minor"], "rationale": "x"}
    verdict = _compare(_gemini({"dropped": lenient, "added": PASS}))
    assert not verdict.equivalent and verdict.dropped.preserved is False


@pytest.mark.parametrize(
    ("status", "fragment"),
    [(429, "rate limit"), (404, "JUDGE_MODEL"), (400, "rejected the request")],
)
def test_api_failures_become_plain_errors(status: int, fragment: str) -> None:
    with pytest.raises(JudgeError, match=fragment):
        _compare(_gemini({}, status=status))


def test_no_key_means_no_judge_never_a_made_up_verdict() -> None:
    judge = GeminiJudge(Settings(gemini_api_key=None))
    assert not judge.available
    with pytest.raises(JudgeError, match="GEMINI_API_KEY"):
        asyncio.run(judge.compare(BASELINE, COMPILED))


def _summary(output: dict, llm_calls: dict) -> RunSummary:
    contract = ContractReport(
        passed=True, required_output_keys=[], missing_output_keys=[], latency_ms=1,
        max_acceptable_latency_ms=10, latency_ok=True, semantic_invariance=1.0,
        min_semantic_similarity=0.95, cache_similarity_threshold=0.88,
    )
    return RunSummary(
        run_id="r", pipeline_type=PipelineType.COMPILED, total_elapsed_ms=1, wall_clock_ms=1,
        node_count=1, cache_hits=0, aggregate_metrics=AggregateMetrics(), contract=contract,
        final_output=output, llm_calls=llm_calls,
    )


def test_offline_stub_outputs_are_recognised() -> None:
    assert is_simulated(_summary({"summary": "[synapse:mock:abcd1234] summary from m"}, {}))
    assert is_simulated(_summary({"summary": "real"}, {"mock": 2}))
    assert not is_simulated(_summary({"summary": "real"}, {"litellm_proxy": 2}))


# --- in the terminal ---------------------------------------------------------------


def _collect(text: str) -> list[dict]:
    async def scenario():
        return [event async for event in run_agent(text, workflow_id=WF)]

    return asyncio.run(scenario())


def _text(events: list[dict]) -> str:
    return "\n".join(e["text"] for e in events if e["type"] == "line")


def test_judge_is_planned_after_the_race_it_judges() -> None:
    assert [s.tool for s in plan("judge the race")] == ["race", "judge"]
    assert [s.tool for s in plan("race it, then judge it")] == ["race", "judge"]
    assert [s.tool for s in plan("does the compiled run give the same answer")] == ["judge"]
    (step,) = plan("judge selftest")
    assert step.calibrate and step.title == "judge selftest"


def test_without_a_key_the_terminal_says_so() -> None:
    assert "judge not configured" in _text(_collect("judge it"))


def test_mock_outputs_are_skipped_not_judged(monkeypatch: pytest.MonkeyPatch) -> None:
    """The offline suite's outputs are stubs: the judge must refuse, and make no call."""
    calls: list[dict] = []
    monkeypatch.setattr(
        terminal, "GeminiJudge",
        lambda: GeminiJudge(_settings(), transport=_gemini({"dropped": PASS, "added": PASS}, calls)),
    )
    out = _text(_collect("race it then judge it"))
    assert "× faster" in out  # the race ran once...
    assert "judge skipped" in out  # ...its outputs were stubs...
    assert calls == []  # ...so nothing was sent to Gemini


def test_a_real_race_gets_a_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        terminal, "GeminiJudge",
        lambda: GeminiJudge(_settings(), transport=_gemini({"dropped": PASS, "added": PASS})),
    )
    monkeypatch.setattr(terminal, "is_simulated", lambda summary: False)
    terminal._LAST_RACE[WF] = (
        _summary(BASELINE, {"litellm_proxy": 6}),
        _summary(COMPILED, {"litellm_proxy": 5}),
        plan("race it", workflow_id=WF)[0],
    )
    out = _text(_collect("judge it"))
    assert "✓ EQUIVALENT · 5/5 · gemini-test" in out
    assert "racing first" not in out  # it judged the stored race


def test_selftest_reports_calibration(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        prompt = json.loads(request.content)["contents"][0]["parts"][0]["text"]
        altered = "rose 14%" in prompt
        verdict = {"preserved": not altered, "score": 2 if altered else 5,
                   "discrepancies": ["41% became 14%"] if altered else [], "rationale": "x"}
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(verdict)}]}}]})

    monkeypatch.setattr(
        terminal, "GeminiJudge", lambda: GeminiJudge(_settings(), transport=httpx.MockTransport(handler))
    )
    out = _text(_collect("judge selftest"))
    assert "✓ faithful paraphrase" in out and "✓ altered figure" in out
    assert "judge calibrated" in out
