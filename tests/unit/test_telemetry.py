"""Unit tests for app.core.telemetry — Section 96 / 123.9."""

from __future__ import annotations


def test_span_noop_without_sdk() -> None:
    """span() must work as a no-op context manager even without opentelemetry installed."""
    from app.core.telemetry import span

    with span("test.operation", {"key": "value"}) as s:
        # Should not raise; s may be a _NoOpSpan or a real span
        assert s is not None


def test_span_noop_no_attributes() -> None:
    from app.core.telemetry import span

    with span("test.no_attrs") as s:
        assert s is not None


def test_configure_telemetry_no_endpoint() -> None:
    """configure_telemetry with no endpoint should not raise."""
    from app.core.telemetry import configure_telemetry
    configure_telemetry(service_name="test-jarvis", otel_endpoint=None)


def test_shutdown_telemetry_safe_before_configure() -> None:
    """shutdown_telemetry must not raise even if configure was never called."""
    from app.core.telemetry import shutdown_telemetry
    shutdown_telemetry()  # should be a no-op


def test_get_tracer_returns_something() -> None:
    from app.core.telemetry import get_tracer
    tracer = get_tracer()
    assert tracer is not None
