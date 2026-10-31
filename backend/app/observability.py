"""OpenTelemetry tracing, exported to Langfuse over OTLP.

Three properties this module has to hold, in order of importance:

1. **It never blocks the run.** Spans go through a `BatchSpanProcessor`, which
   buffers in memory and flushes from its own background thread. Nothing on the
   event loop ever waits for Langfuse, so the SSE stream keeps its cadence even
   if the collector is slow or gone.
2. **It never fails the run.** Missing packages, missing credentials or a dead
   collector all degrade to no-op spans. Telemetry about a pipeline must not be
   able to break the pipeline.
3. **It is honest about time.** Spans carry nanosecond start/end from OTel
   itself, so the microsecond resolution the PRD asks for is real rather than
   reconstructed from our own millisecond bookkeeping.

Langfuse ingests OTLP directly at `/api/public/otel/v1/traces`, authenticated
with Basic auth over the public/secret key pair. That is why there is no
`langfuse` SDK call anywhere here: the SDK would be a second, redundant path to
the same backend, and spans we already produce are the better source.
"""

import base64
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .config import Settings, get_settings

logger = logging.getLogger(__name__)

SERVICE_NAME = "synapse-compiler"
OTLP_TRACES_PATH = "/api/public/otel/v1/traces"

_tracer: Any = None
_configured = False


def configure_tracing(settings: Settings | None = None) -> bool:
    """Install the tracer provider. Returns True when spans will be exported.

    Called once from `create_app`. Safe to call again; the second call is a
    no-op so a reload cannot stack duplicate exporters.
    """
    global _tracer, _configured
    if _configured:
        return _tracer is not None
    _configured = True

    settings = settings or get_settings()
    if not settings.tracing_enabled:
        logger.info("tracing disabled by configuration")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        logger.info("opentelemetry not installed (%s); spans are no-ops", exc)
        return False

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": SERVICE_NAME,
                "deployment.environment": settings.environment,
            }
        )
    )

    exporter = _langfuse_exporter(settings, OTLPSpanExporter)
    if exporter is None:
        logger.info(
            "langfuse credentials absent; tracing stays in-process "
            "(spans are created and timed, but nothing is exported)"
        )
    else:
        # Batched and off-thread: the export never joins the event loop.
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(SERVICE_NAME)
    return exporter is not None


def _langfuse_exporter(settings: Settings, exporter_cls: Any) -> Any:
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    token = base64.b64encode(
        f"{settings.langfuse_public_key}:{settings.langfuse_secret_key}".encode()
    ).decode()
    endpoint = settings.langfuse_host.rstrip("/") + OTLP_TRACES_PATH
    logger.info("exporting spans to langfuse at %s", endpoint)
    return exporter_cls(
        endpoint=endpoint,
        headers={"Authorization": f"Basic {token}"},
        timeout=settings.tracing_export_timeout_s,
    )


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Any]:
    """Time a block of work as a span.

    Yields the span so the caller can attach what it only learns afterwards --
    token counts, a cache similarity, a breaker trip. Yields None when tracing
    is off, so every call site has to tolerate that; `record` does it for them.
    """
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as active:
        record(active, **attributes)
        yield active


def record(active: Any, **attributes: Any) -> None:
    """Attach attributes to a span, skipping Nones and tolerating no span."""
    if active is None:
        return
    for key, value in attributes.items():
        if value is not None:
            active.set_attribute(key, value)


def fail(active: Any, exc: BaseException) -> None:
    """Mark a span as failed. Kept separate so call sites stay one-liners."""
    if active is None:
        return
    active.record_exception(exc)
    try:
        from opentelemetry.trace import Status, StatusCode

        active.set_status(Status(StatusCode.ERROR, str(exc)))
    except ImportError:  # pragma: no cover - only if the SDK vanished mid-run
        pass
