"""LiteLLM gateway wrapper with offline Ollama routing and mock fallback.

Routing order for a single completion:
  1. `llm_offline_mode` is set            -> deterministic mock, no network.
  2. model is `ollama/*`                  -> local Ollama via LiteLLM.
  3. anything else                        -> LiteLLM proxy (spend caps, tracing).
  4. LiteLLM missing or the call raises    -> deterministic mock.

Step 4 is the point of the whole module: the venue network can disappear
mid-demo and the pipeline still produces stable, reproducible output.
"""

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Literal

import httpx

from ..config import Settings, get_settings
from ..runtime.profile import COST_PER_TOKEN_USD

logger = logging.getLogger(__name__)

LLMSource = Literal["litellm_proxy", "ollama", "mock"]
PROBE_TIMEOUT_S = 1.5


class BudgetExceededError(RuntimeError):
    """Financial circuit breaker tripped (PRD section 7.4)."""


@dataclass(slots=True)
class RunBudget:
    """Per-workflow spend ledger enforced before each outbound call."""

    limit_usd: float
    spent_usd: float = 0.0

    def charge(self, cost_usd: float) -> None:
        if self.spent_usd + cost_usd > self.limit_usd:
            raise BudgetExceededError(
                f"run budget ${self.limit_usd} exhausted "
                f"(spent ${self.spent_usd:.6f}, next call ${cost_usd:.6f})"
            )
        self.spent_usd += cost_usd


@dataclass(slots=True)
class LLMResult:
    text: str
    tokens_consumed: int
    cost_usd: float
    latency_ms: int
    source: LLMSource
    model: str


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
    ) -> LLMResult:
        model = model or "ollama/qwen2.5:7b"
        started = time.perf_counter()

        if self.settings.llm_offline_mode:
            result = self._mock(prompt, system_prompt, model, started)
        else:
            result = await self._dispatch(prompt, system_prompt, model, max_tokens, started)

        if budget is not None:
            budget.charge(result.cost_usd)
        return result

    async def _dispatch(
        self, prompt: str, system_prompt: str, model: str, max_tokens: int, started: float
    ) -> LLMResult:
        try:
            import litellm
        except ImportError:
            logger.warning("litellm is not installed; serving a deterministic mock")
            return self._mock(prompt, system_prompt, model, started)

        is_local = model.startswith("ollama/")
        api_base = (
            self.settings.local_ollama_url if is_local else self.settings.litellm_proxy_url
        )
        messages = (
            [{"role": "system", "content": system_prompt}] if system_prompt else []
        ) + [{"role": "user", "content": prompt}]

        try:
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                api_base=api_base,
                max_tokens=max_tokens,
            )
        except Exception as exc:  # offline resilience: never fail the pipeline
            logger.warning("llm call failed (%s); serving a deterministic mock", exc)
            return self._mock(prompt, system_prompt, model, started)

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
        self, prompt: str, system_prompt: str, model: str, started: float
    ) -> LLMResult:
        seed = hashlib.sha256(f"{model}|{system_prompt}|{prompt}".encode()).hexdigest()
        tokens = 180 + int(seed[:4], 16) % 720
        return LLMResult(
            text=(
                f"[synapse:mock:{seed[:8]}] deterministic response for "
                f"{model} :: {(system_prompt or prompt)[:96]}"
            ),
            tokens_consumed=tokens,
            cost_usd=round(tokens * COST_PER_TOKEN_USD, 6),
            latency_ms=_elapsed_ms(started),
            source="mock",
            model=model,
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


async def _reachable(client: httpx.AsyncClient, url: str) -> bool:
    try:
        return (await client.get(url)).status_code < 500
    except httpx.HTTPError:
        return False


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
