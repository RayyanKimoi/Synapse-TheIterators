"""Slack alerts: the payload is right, and nothing it can do breaks a run.

No mock library: httpx ships MockTransport, and `send_alert` takes a transport
for exactly this reason -- the same injection the judge's tests use.
"""

import httpx
import pytest

from app import alerts
from app.config import Settings

PAYLOAD_KWARGS = dict(
    run_id="run_abc123",
    failed_node="synth_report",
    reason="LLM Timeout",
    spent_usd=0.4231,
    budget_usd=0.5,
    dashboard_base_url="http://localhost:3000",
)


def _settings(webhook: str = "https://hooks.slack.com/services/T/B/x") -> Settings:
    return Settings(slack_webhook_url=webhook, dashboard_base_url="http://localhost:3000")


def test_payload_carries_every_field_and_the_deep_link() -> None:
    payload = alerts.build_alert_payload(**PAYLOAD_KWARGS)

    header, section, actions = payload["blocks"]
    assert header["text"]["text"] == "🚨 SYNAPSE Alert: Run Halted"
    fields = " ".join(field["text"] for field in section["fields"])
    assert "run_abc123" in fields
    assert "synth_report" in fields
    assert "LLM Timeout" in fields
    assert "$0.4231 / $0.5000" in fields
    assert (
        actions["elements"][0]["url"]
        == "http://localhost:3000/dashboard?run_id=run_abc123"
    )
    # Fallback text for clients that do not render blocks.
    assert "run_abc123" in payload["text"]


def test_breaker_payload_has_its_own_header() -> None:
    payload = alerts.build_alert_payload(**PAYLOAD_KWARGS, breaker=True)
    assert payload["blocks"][0]["text"]["text"] == "⚠️ Circuit Breaker Triggered"


def test_trailing_slash_does_not_double_up_in_the_link() -> None:
    payload = alerts.build_alert_payload(
        **(PAYLOAD_KWARGS | {"dashboard_base_url": "https://synapse.app/"})
    )
    assert (
        payload["blocks"][2]["elements"][0]["url"]
        == "https://synapse.app/dashboard?run_id=run_abc123"
    )


@pytest.mark.asyncio
async def test_send_posts_the_payload_and_reports_success() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="ok")

    payload = alerts.build_alert_payload(**PAYLOAD_KWARGS)
    sent = await alerts.send_alert(
        payload, settings=_settings(), transport=httpx.MockTransport(handler)
    )

    assert sent is True
    assert len(seen) == 1
    assert seen[0].url == "https://hooks.slack.com/services/T/B/x"


@pytest.mark.asyncio
async def test_network_failure_is_swallowed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slack unreachable")

    sent = await alerts.send_alert(
        {}, settings=_settings(), transport=httpx.MockTransport(handler)
    )
    assert sent is False


@pytest.mark.asyncio
async def test_slack_error_status_is_swallowed() -> None:
    sent = await alerts.send_alert(
        {},
        settings=_settings(),
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
    )
    assert sent is False


@pytest.mark.asyncio
async def test_missing_webhook_skips_without_a_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request may be made without a webhook URL")

    sent = await alerts.send_alert(
        {}, settings=_settings(""), transport=httpx.MockTransport(handler)
    )
    assert sent is False


@pytest.mark.asyncio
async def test_notify_is_a_no_op_when_unconfigured() -> None:
    """The runner calls this on every halted run; by default there is no webhook."""
    alerts.notify(**{k: v for k, v in PAYLOAD_KWARGS.items() if k != "dashboard_base_url"})
    assert not alerts._in_flight
