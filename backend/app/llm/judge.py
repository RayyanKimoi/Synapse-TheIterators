"""LLM-as-a-judge: does the compiled pipeline give the same answer as the baseline?

The run contract checks structure (required keys), latency and how similar each
cache admission was -- none of which look at what the two pipelines actually
*said*. Prompt fusion changes what the model sees, and a cache hit serves an
answer to a neighbouring question, so a compiled run can drift while every
structural check still passes. This module asks an independent model (Gemini)
to compare the two final outputs.

The comparison runs in both directions, concurrently:
  baseline -> compiled   catches what the compiled run dropped or changed
  compiled -> baseline   catches what it added that the baseline never said
and the verdict is "equivalent" only when both agree. One direction alone would
pass a candidate that kept every baseline fact and invented more.

It never fabricates a verdict. With no key it reports itself unavailable, and
callers are expected to skip offline-mock outputs (`is_simulated`), where
"the same answer" is a comparison of placeholders and means nothing.
"""

import asyncio
import json
import time
from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..models.telemetry import RunSummary

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
# Long reports are compared whole; this only stops a runaway payload.
MAX_OUTPUT_CHARS = 24_000
MOCK_MARKERS = ("[synapse:mock:", "offline_stub")
RETRYABLE = {429, 500, 503}

_SYSTEM = """You verify that a compiler optimization preserved an AI pipeline's output.
REFERENCE and CANDIDATE are two answers to the same request. Decide whether every
fact, figure, named entity, date, risk and conclusion in REFERENCE is also present
in CANDIDATE with the same meaning.

Wording, ordering, formatting and length may differ freely. A changed number, a
dropped item, a different entity or a reversed conclusion is a discrepancy.
Information that appears only in CANDIDATE is not your concern here.

score: 5 = fully preserved; 4 = only trivial omissions; 3 = a minor fact lost or
altered; 2 = a material fact lost or altered; 1 = the conclusions differ.
preserved is true only for scores 4 and 5. Write each discrepancy as one short
sentence naming the fact. Leave discrepancies empty when there are none."""

_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "preserved": {"type": "BOOLEAN"},
        "score": {"type": "INTEGER"},
        "discrepancies": {"type": "ARRAY", "items": {"type": "STRING"}},
        "rationale": {"type": "STRING"},
    },
    "required": ["preserved", "score", "discrepancies", "rationale"],
}


class JudgeError(RuntimeError):
    """The judge could not produce a verdict; the message says why, plainly."""


class Direction(BaseModel):
    preserved: bool
    score: int
    discrepancies: list[str]
    rationale: str


class Verdict(BaseModel):
    equivalent: bool
    score: int
    # Labelled by direction: "missing in compiled: ..." / "only in compiled: ..."
    discrepancies: list[str]
    model: str
    latency_ms: int
    tokens: int
    dropped: Direction  # baseline -> compiled
    added: Direction  # compiled -> baseline


class Calibration(BaseModel):
    case: str
    expected_equivalent: bool
    verdict: Verdict

    @property
    def correct(self) -> bool:
        return self.verdict.equivalent == self.expected_equivalent


def is_simulated(summary: RunSummary) -> bool:
    """True when a run's output came from offline stubs rather than a model."""
    if summary.llm_calls.get("mock"):
        return True
    text = json.dumps(summary.final_output, default=str)
    return any(marker in text for marker in MOCK_MARKERS)


def _render(output: Mapping[str, Any] | str) -> str:
    text = output if isinstance(output, str) else json.dumps(output, indent=2, ensure_ascii=False, default=str)
    return text if len(text) <= MAX_OUTPUT_CHARS else text[:MAX_OUTPUT_CHARS] + "\n…[truncated]"


class GeminiJudge:
    def __init__(self, settings: Settings | None = None, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings or get_settings()
        self.model = self.settings.judge_model
        # Tests inject a MockTransport; production uses the default network one.
        self._transport = transport

    @property
    def available(self) -> bool:
        key = self.settings.gemini_api_key
        return bool(key and key.strip())

    async def compare(
        self,
        baseline: Mapping[str, Any] | str,
        compiled: Mapping[str, Any] | str,
        *,
        query: str = "",
        required_keys: list[str] | tuple[str, ...] = (),
    ) -> Verdict:
        if not self.available:
            raise JudgeError("no judge configured -- set GEMINI_API_KEY in the repo-root .env")
        started = time.perf_counter()
        async with self._client() as client:
            (dropped, dropped_tokens), (added, added_tokens) = await asyncio.gather(
                self._direction(client, baseline, compiled, query, required_keys),
                self._direction(client, compiled, baseline, query, required_keys),
            )
        return Verdict(
            equivalent=dropped.preserved and added.preserved,
            score=min(dropped.score, added.score),
            discrepancies=[f"missing in compiled: {item}" for item in dropped.discrepancies]
            + [f"only in compiled: {item}" for item in added.discrepancies],
            model=self.model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            tokens=dropped_tokens + added_tokens,
            dropped=dropped,
            added=added,
        )

    async def calibrate(self) -> list[Calibration]:
        """Runs the judge on pairs whose answer is known. A judge that cannot
        pass a faithful paraphrase and fail an altered figure is not to be
        trusted on real runs -- this is the check before relying on it."""

        async def one(case: str, reference: dict, candidate: dict, expected: bool) -> Calibration:
            verdict = await self.compare(reference, candidate, query=_CALIBRATION_QUERY)
            return Calibration(case=case, expected_equivalent=expected, verdict=verdict)

        return list(await asyncio.gather(*(one(*case) for case in _CALIBRATION)))

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=GEMINI_BASE,
            timeout=self.settings.judge_timeout_s,
            transport=self._transport,
            # A header rather than ?key=, so the key never lands in a URL or log.
            headers={"x-goog-api-key": (self.settings.gemini_api_key or "").strip()},
        )

    async def _direction(
        self,
        client: httpx.AsyncClient,
        reference: Mapping[str, Any] | str,
        candidate: Mapping[str, Any] | str,
        query: str,
        required_keys: list[str] | tuple[str, ...],
    ) -> tuple[Direction, int]:
        prompt = (
            f"Request: {query or '(not recorded)'}\n"
            f"Required output keys: {', '.join(required_keys) or '(none)'}\n\n"
            f"REFERENCE:\n{_render(reference)}\n\nCANDIDATE:\n{_render(candidate)}"
        )
        body = {
            "systemInstruction": {"parts": [{"text": _SYSTEM}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": _SCHEMA,
            },
        }
        data = await self._post(client, body)
        try:
            text = "".join(part.get("text", "") for part in data["candidates"][0]["content"]["parts"])
            direction = Direction.model_validate_json(text)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            reason = (data.get("candidates") or [{}])[0].get("finishReason", "unknown")
            raise JudgeError(f"{self.model} returned no usable verdict (finish reason {reason})") from exc
        direction.score = max(1, min(5, direction.score))
        # The schema cannot tie the two fields together, so enforce the rubric.
        direction.preserved = direction.preserved and direction.score >= 4
        return direction, int(data.get("usageMetadata", {}).get("totalTokenCount", 0))

    async def _post(self, client: httpx.AsyncClient, body: dict[str, Any]) -> dict[str, Any]:
        path = f"/models/{self.model}:generateContent"
        for attempt in range(2):
            try:
                response = await client.post(path, json=body)
            except httpx.TimeoutException as exc:
                raise JudgeError(f"{self.model} timed out after {self.settings.judge_timeout_s:g}s") from exc
            except httpx.HTTPError as exc:
                raise JudgeError(f"could not reach Gemini ({type(exc).__name__})") from exc
            if response.status_code in RETRYABLE and attempt == 0:
                await asyncio.sleep(2.0)  # free-tier bursts clear within seconds
                continue
            if response.status_code == 200:
                return response.json()
            raise JudgeError(_explain(response, self.model))
        raise JudgeError("unreachable")  # pragma: no cover - the loop always returns or raises


def _explain(response: httpx.Response, model: str) -> str:
    status = response.status_code
    if status == 429:
        return "Gemini free-tier rate limit hit -- wait a minute and retry"
    if status == 404:
        return f"model {model} is not available to this key -- set JUDGE_MODEL"
    if status in (400, 401, 403):
        try:
            message = response.json()["error"]["message"]
        except (ValueError, KeyError, TypeError):
            message = response.text[:160]
        return f"Gemini rejected the request ({status}): {message}"
    return f"Gemini responded {status}"


# --- calibration -----------------------------------------------------------------

_CALIBRATION_QUERY = "Brief me on NVIDIA's latest data-center results and the main risks."
_REFERENCE = {
    "summary": "NVIDIA's data-center revenue rose 41% year over year to $18.4B in Q3, driven by H100 demand.",
    "risk_factors": [
        "US export controls on advanced chips sold to China",
        "Customer concentration: the four largest cloud buyers are about half of data-center sales",
    ],
}
_CALIBRATION = (
    (
        "faithful paraphrase",
        _REFERENCE,
        {
            "summary": "In Q3, NVIDIA grew data-center sales 41% from a year earlier, to $18.4 billion, on strong H100 demand.",
            "risk_factors": [
                "Roughly half of data-center revenue comes from four cloud customers",
                "Export restrictions on advanced chips to China",
            ],
        },
        True,
    ),
    (
        "altered figure, dropped risk",
        _REFERENCE,
        {
            "summary": "NVIDIA's data-center revenue rose 14% year over year to $18.4B in Q3, driven by H100 demand.",
            "risk_factors": ["US export controls on advanced chips sold to China"],
        },
        False,
    ),
)
