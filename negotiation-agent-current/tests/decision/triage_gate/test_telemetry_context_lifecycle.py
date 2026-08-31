import time
from typing import Any, Dict, List
import pytest

from decision.triage_gate.telemetry import TransportTelemetrySink
from decision.triage_gate.telemetry_context import ManagedTelemetrySession
from decision.triage_gate.telemetry_drain import DrainSummary

# NOTE: rewritten against the actual ManagedTelemetrySession contract
# (decision/triage_gate/telemetry_context.py). The originally-supplied version
# of this file targeted a `record_step`/`set_terminal_status` session-tracing
# API that does not exist in the built implementation -- the real class is a
# context manager that starts/stops a PeriodicTelemetryDrainScheduler around a
# TransportTelemetrySink. See conversation record for the reconciliation.


def test_managed_telemetry_session_starts_and_stops_drain_scheduler_cleanly() -> None:
    """
    Control Invariant: Entering the session activates the background periodic
    drain scheduler (is_active becomes True); exiting stops it deterministically,
    produces a final DrainSummary, and forwards any buffered events to forwarder_fn.
    """
    sink = TransportTelemetrySink(capacity=100)
    collected: List[Dict[str, Any]] = []

    def forwarder(batch: List[Dict[str, Any]]) -> None:
        collected.extend(batch)

    with ManagedTelemetrySession(
        telemetry_sink=sink,
        forwarder_fn=forwarder,
        drain_interval_seconds=0.02,
        stop_timeout_seconds=1.0,
    ) as session:
        assert session.is_active is True
        sink.record_event(event_type="OP", event_id="evt-1", duration_ms=1.0)
        time.sleep(0.06)  # allow at least one periodic drain tick

    assert session.is_active is False
    assert session.final_summary is not None
    assert isinstance(session.final_summary, DrainSummary)
    assert any(e.get("event_id") == "evt-1" for e in collected)


def test_managed_telemetry_session_propagates_exception_and_still_tears_down() -> None:
    """
    Control Invariant: An unhandled exception raised inside the session body
    propagates normally to the caller, but the scheduler is still torn down
    (is_active returns to False) rather than leaking a background thread.
    """
    sink = TransportTelemetrySink(capacity=50)

    with pytest.raises(ValueError, match="boom"):
        with ManagedTelemetrySession(
            telemetry_sink=sink,
            forwarder_fn=lambda batch: None,
            drain_interval_seconds=1.0,
            stop_timeout_seconds=1.0,
        ) as session:
            assert session.is_active is True
            raise ValueError("boom")

    assert session.is_active is False
