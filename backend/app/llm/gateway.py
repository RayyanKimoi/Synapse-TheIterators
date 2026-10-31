"""LiteLLM gateway: offline Ollama routing, budget guardrails, mock fallback.

Order of operations for a single completion:
  0. The run budget reserves the call's worst-case cost. If that would exceed
     the limit the circuit breaker trips and no request is sent.
  1. `llm_offline_mode` is set            -> deterministic mock, no network.
  2. model is `ollama/*`                  -> local Ollama via LiteLLM.
  3. anything else                        -> LiteLLM proxy (spend caps, tracing).
  4. LiteLLM missing or the call raises    -> `LLMUnavailableError`.

The mock is reachable only through step 1, as an explicit choice. It makes the
test suite deterministic and lets the arena be rehearsed with no network at
all. It is never a fallback for a live run: a run with `llm_offline_mode` off
reports a failed node instead of quietly substituting invented text, because
nothing downstream -- the contract check, the semantic cache that would store
the answer, the judge watching the arena -- can tell the difference.
"""

import asyncio
import hashlib
import importlib
import json
import logging
import math
import time
from dataclasses import dataclass
from types import ModuleType
from typing import Literal

import httpx

from ..config import Settings, get_settings
from ..models.ir import WorkflowIR
from ..runtime.profile import COST_PER_TOKEN_USD

logger = logging.getLogger(__name__)

LLMSource = Literal["litellm_proxy", "ollama", "mock"]
DEFAULT_MODEL = "ollama/qwen2.5:7b"
PROBE_TIMEOUT_S = 1.5
# Rough English average; only used to size the pre-call budget reservation.
CHARS_PER_TOKEN = 4

_litellm: ModuleType | None = None


class BudgetExceededError(RuntimeError):
    """Financial circuit breaker tripped (PRD: LiteLLM proxy and financial circuit breakers)."""


class LLMUnavailableError(RuntimeError):
    """A live model call failed and no result was produced.

    Raised instead of returning a fabricated completion. Running live, an
    invented answer is indistinguishable from a real one to everything
    downstream -- the contract check, the semantic cache that would store it,
    and the judge reading the arena. A failed node is at least honest.
    """


@dataclass(slots=True)
class RunBudget:
    """Per-run spend ledger with reservations.

    A call reserves its worst-case cost before it is sent and settles the actual
    cost when it returns, so nodes dispatched concurrently by the Ready-Node
    scheduler cannot jointly overspend. Once tripped, the breaker stays open for
    the rest of the run.
    """

    limit_usd: float
    spent_usd: float = 0.0
    reserved_usd: float = 0.0
    tripped: bool = False

    def reserve(self, amount_usd: float) -> None:
        committed = self.spent_usd + self.reserved_usd
        if self.tripped:
            raise BudgetExceededError(
                f"circuit breaker open: run budget ${self.limit_usd:.4f} already exhausted"
            )
        if committed + amount_usd > self.limit_usd:
            self.tripped = True
            raise BudgetExceededError(
                f"run budget ${self.limit_usd:.4f} would be exceeded "
                f"(committed ${committed:.6f}, next call up to ${amount_usd:.6f})"
            )
        self.reserved_usd += amount_usd

    def settle(self, reserved_usd: float, actual_usd: float) -> None:
        self.reserved_usd = max(self.reserved_usd - reserved_usd, 0.0)
        self.spent_usd += actual_usd
        if self.spent_usd > self.limit_usd:
            self.tripped = True


@dataclass(frozen=True, slots=True)
class Guardrails:
    """Run-level guardrail thresholds, resolved once from the IR and settings."""

    budget_limit_usd: float
    cache_similarity_threshold: float

    @classmethod
    def resolve(cls, workflow: WorkflowIR, settings: Settings | None = None) -> "Guardrails":
        settings = settings or get_settings()
        return cls(
            # The IR may ask for less than the deployment ceiling, never more.
            budget_limit_usd=min(
                workflow.budget_limit_usd, settings.max_budget_per_workflow_usd
            ),
            cache_similarity_threshold=settings.semantic_cache_similarity_threshold,
        )


@dataclass(slots=True)
class LLMResult:
    text: str
    tokens_consumed: int
    cost_usd: float
    latency_ms: int
    source: LLMSource
    model: str
    fallback_reason: str | None = None


def estimate_cost_usd(system_prompt: str, prompt: str, max_tokens: int) -> float:
    """Worst-case cost of one call: the whole prompt in, `max_tokens` out."""
    prompt_tokens = math.ceil((len(system_prompt) + len(prompt)) / CHARS_PER_TOKEN)
    return (prompt_tokens + max_tokens) * COST_PER_TOKEN_USD


class LLMGateway:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def complete(
        self,
        *,
        prompt: str,
        system_prompt: str = "",
        model: str | None = None,
        max_tokens: int = 512,
        budget: RunBudget | None = None,
        response_keys: list[str] | None = None,
    ) -> LLMResult:
        """One completion.

        Raises `BudgetExceededError` before any request is sent when `budget`
        cannot cover the call's worst case. `response_keys` asks for a single
        JSON object with exactly those keys.
        """
        model = model or DEFAULT_MODEL
        if response_keys:
            system_prompt = _with_json_contract(system_prompt, response_keys)

        reserved = estimate_cost_usd(system_prompt, prompt, max_tokens)
        if budget is not None:
            budget.reserve(reserved)

        started = time.perf_counter()
        try:
            if self.settings.llm_offline_mode:
                result = self._mock(prompt, system_prompt, model, response_keys, started)
            else:
                result = await self._dispatch(
                    prompt, system_prompt, model, max_tokens, response_keys, started
                )
        except BaseException:
            # Cancelled mid-flight (e.g. the SSE client disconnected): release the hold.
            if budget is not None:
                budget.settle(reserved, 0.0)
            raise

        if budget is not None:
            budget.settle(reserved, result.cost_usd)
        return result

    async def _dispatch(
        self,
        prompt: str,
        system_prompt: str,
        model: str,
        max_tokens: int,
        response_keys: list[str] | None,
        started: float,
    ) -> LLMResult:
        litellm = await _load_litellm()
        if litellm is None:
            raise LLMUnavailableError(
                "litellm is not installed, so no live call can be made"
            )

        is_local = model.startswith("ollama/")
        api_base = (
            self.settings.local_ollama_url if is_local else self.settings.litellm_proxy_url
        )
        messages = (
            [{"role": "system", "content": system_prompt}] if system_prompt else []
        ) + [{"role": "user", "content": prompt}]

        call: dict[str, object] = {
            "model": model,
            "messages": messages,
            "api_base": api_base,
            "max_tokens": max_tokens,
        }
        if not is_local:
            # The proxy authenticates every request; a local Ollama does not.
            # Without this the proxy answers 401 and the result is a mock that
            # looks like a network failure.
            call["api_key"] = self.settings.openai_api_key

        try:
            response = await litellm.acompletion(**call)
        except Exception as exc:
            logger.warning("live call to %s failed: %s", model, exc)
            raise LLMUnavailableError(f"{model}: {type(exc).__name__}: {exc}") from exc

        usage = getattr(response, "usage", None)
        tokens = int(getattr(usage, "total_tokens", 0) or 0)
        try:
            cost = float(litellm.completion_cost(completion_response=response))
        except Exception:
            cost = round(tokens * COST_PER_TOKEN_USD, 6)

        return LLMResult(
            text=response.choices[0].message.content or "",
            tokens_consumed=tokens,
            cost_usd=round(cost, 6),
            latency_ms=_elapsed_ms(started),
            source="ollama" if is_local else "litellm_proxy",
            model=model,
        )

    def _mock(
        self,
        prompt: str,
        system_prompt: str,
        model: str,
        response_keys: list[str] | None,
        started: float,
        fallback: str | None = None,
    ) -> LLMResult:
        if fallback:
            logger.warning("llm call to %s degraded to mock: %s", model, fallback)
        seed = hashlib.sha256(f"{model}|{system_prompt}|{prompt}".encode()).hexdigest()
        tokens = 180 + int(seed[:4], 16) % 720
        if response_keys:
            # Stands in for a model that follows the JSON contract it was given.
            text = json.dumps(
                {key: f"[synapse:mock:{seed[:8]}] {key} from {model}" for key in response_keys}
            )
        else:
            text = (
                f"[synapse:mock:{seed[:8]}] deterministic response for "
                f"{model} :: {(system_prompt or prompt)[:96]}"
            )
        return LLMResult(
            text=text,
            tokens_consumed=tokens,
            cost_usd=round(tokens * COST_PER_TOKEN_USD, 6),
            latency_ms=_elapsed_ms(started),
            source="mock",
            model=model,
            fallback_reason=fallback,
        )

    async def probe(self) -> dict[str, object]:
        """Backend reachability for the top-bar offline badge (PRD 9.1)."""
        if self.settings.llm_offline_mode:
            return {"offline_mode": True, "ollama": False, "litellm_proxy": False}
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_S) as client:
            return {
                "offline_mode": False,
                "ollama": await _reachable(client, f"{self.settings.local_ollama_url}/api/tags"),
                "litellm_proxy": await _reachable(
                    client, f"{self.settings.litellm_proxy_url}/health"
                ),
            }


async def _load_litellm() -> ModuleType | None:
    """Import litellm in a worker thread: it takes seconds, and doing it on the
    event loop would freeze every SSE stream in flight."""
    global _litellm
    if _litellm is None:
        try:
            _litellm = await asyncio.to_thread(importlib.import_module, "litellm")
        except ImportError:
            return None
    return _litellm


def _with_json_contract(system_prompt: str, keys: list[str]) -> str:
    contract = (
        "Respond with only a single JSON object whose keys are exactly: "
        f"{', '.join(keys)}. Every value must be a string."
    )
    return f"{system_prompt}\n\n{contract}" if system_prompt else contract


async def _reachable(client: httpx.AsyncClient, url: str) -> bool:
    try:
        return (await client.get(url)).status_code < 500
    except httpx.HTTPError:
        return False


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
