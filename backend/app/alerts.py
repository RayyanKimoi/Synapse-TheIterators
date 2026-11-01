"""Best-effort Slack alerts for runs that halted.

Two properties, borrowed from observability.py for the same reason: an alert
*about* a broken run must never be the thing that breaks the run.

1. **It never fails the run.** No webhook configured, a dead Slack, a 500, a
   timeout -- every path logs a warning and returns False.
2. **It never blocks the run.** `notify` schedules the post and returns
   immediately, so the SSE stream keeps its cadence while the HTTP call is in
   flight. Nothing downstream waits on, or reads, the result.

The webhook URL is a secret and stays server-side: the frontend only ever sees
the dashboard deep link that the payload carries back to it.
"""

import asyncio
import logging
from typing import Any

import httpx

from .config import Settings, get_settings

logger = logging.getLogger(__name__)

TIMEOUT_S = 2.0

# create_task keeps only a weak reference, so a fire-and-forget task can be
# garbage collected mid-flight. Holding it until it finishes is the fix.
_in_flight: set[asyncio.Task[bool]] = set()


def build_alert_payload(
    *,
    run_id: str,
    failed_node: str,
    reason: str,
    spent_usd: float,
    budget_usd: float,
    dashboard_base_url: str,
    breaker: bool = False,
) -> dict[str, Any]:
    """The Slack Block Kit body for one halted run. Pure."""
    title = (
        "⚠️ Circuit Breaker Triggered" if breaker else "🚨 SYNAPSE Alert: Run Halted"
    )
    fields = [
        ("Run ID", f"`{run_id}`"),
        ("Failed Node", f"`{failed_node}`"),
        ("Reason", reason),
        ("Spend / Budget", f"${spent_usd:.4f} / ${budget_usd:.4f}"),
    ]
    return {
        # Notification text for clients that cannot render blocks.
        "text": f"{title} — run {run_id}: {reason}",
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": title}},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*{label}*\n{value}"}
                    for label, value in fields
                ],
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View trace"},
                        "url": f"{dashboard_base_url.rstrip('/')}/dashboard?run_id={run_id}",
                    }
                ],
            },
        ],
    }


async def send_alert(
    payload: dict[str, Any],
    *,
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bool:
    """POST one payload to the configured webhook. True only on a 2xx."""
    settings = settings or get_settings()
    webhook = settings.slack_webhook_url
    if not webhook:
        logger.debug("slack alert skipped: SLACK_WEBHOOK_URL is not set")
        return False
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=transport) as client:
            response = await client.post(webhook, json=payload)
            response.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 -- an alert may not raise into the run
        logger.warning("slack alert failed: %s", exc)
        return False


def notify(**kwargs: Any) -> None:
    """Build and post an alert in the background. Returns at once, never raises.

    Keyword arguments are `build_alert_payload`'s, minus `dashboard_base_url`,
    which comes from settings.
    """
    try:
        settings = get_settings()
        if not settings.slack_webhook_url:
            return
        payload = build_alert_payload(
            dashboard_base_url=settings.dashboard_base_url, **kwargs
        )
        task = asyncio.create_task(send_alert(payload, settings=settings))
        _in_flight.add(task)
        task.add_done_callback(_in_flight.discard)
    except Exception as exc:  # noqa: BLE001
        logger.warning("slack alert could not be scheduled: %s", exc)
