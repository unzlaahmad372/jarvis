"""OpenTelemetry bootstrap — Section 96 / 123.9.

Phase 0 establishes the abstraction and correlation-ID plumbing.
A real OTLP exporter is wired only when JARVIS_OTEL_ENDPOINT is set.
If no collector is configured, JARVIS continues with structured logging only.

NEVER record in spans:
  - document contents
  - prompts containing private data
  - passwords / tokens / API keys
  - raw tool output containing secrets
  - raw voice recordings / speaker embeddings
"""

from __future__ import annotations

import contextlib
from collections.abc import Generator
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Lightweight span abstraction — works with or without opentelemetry installed
# ---------------------------------------------------------------------------

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _OTEL_AVAILABLE = False


_tracer_provider: Any = None
_tracer: Any = None


def configure_telemetry(
    service_name: str = "jarvis",
    otel_endpoint: str | None = None,
) -> None:
    """Bootstrap OpenTelemetry.  Called once at application startup.

    If opentelemetry-sdk is not installed or no endpoint is configured,
    this is a no-op and JARVIS falls back to structured logging.
    """
    global _tracer_provider, _tracer  # noqa: PLW0603

    if not _OTEL_AVAILABLE:
        logger.info("otel_unavailable", reason="opentelemetry-sdk not installed; using logs only")
        return

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    if otel_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=otel_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("otel_configured", endpoint=otel_endpoint)
        except ImportError:
            logger.warning(
                "otel_otlp_unavailable",
                reason="opentelemetry-exporter-otlp not installed; falling back to console",
            )
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        # No external collector — spans are no-ops unless debug console is wanted
        logger.info("otel_no_endpoint", note="telemetry active but no exporter configured")

    trace.set_tracer_provider(provider)
    _tracer_provider = provider
    _tracer = trace.get_tracer(service_name)


def get_tracer() -> Any:
    """Return the configured tracer, or a no-op stub if OTel is unavailable."""
    if _tracer is not None:
        return _tracer
    return _NoOpTracer()


@contextlib.contextmanager
def span(
    name: str,
    attributes: dict[str, str | int | float | bool] | None = None,
) -> Generator[Any, None, None]:
    """Context manager that creates a span when OTel is available.

    Falls back to a no-op context when OTel is not configured.
    Attributes must be pre-sanitised — never pass secrets or private content.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as s:
        if attributes and _OTEL_AVAILABLE and not isinstance(s, _NoOpSpan):
            for k, v in attributes.items():
                s.set_attribute(k, v)
        yield s


def shutdown_telemetry() -> None:
    """Flush and shut down the tracer provider on application exit."""
    if _tracer_provider is not None and _OTEL_AVAILABLE:
        with contextlib.suppress(Exception):
            _tracer_provider.shutdown()


# ---------------------------------------------------------------------------
# No-op stubs used when OTel SDK is absent
# ---------------------------------------------------------------------------

class _NoOpSpan:
    def set_attribute(self, key: str, value: object) -> None:  # noqa: ARG002
        pass

    def record_exception(self, exc: BaseException) -> None:  # noqa: ARG002
        pass

    def set_status(self, *args: Any, **kwargs: Any) -> None:
        pass


class _NoOpTracer:
    @contextlib.contextmanager
    def start_as_current_span(self, name: str) -> Generator[_NoOpSpan, None, None]:  # noqa: ARG002
        yield _NoOpSpan()
