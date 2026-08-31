import threading
import time
from typing import List
import pytest

from decision.triage_gate.telemetry import TransportTelemetrySink
from decision.triage_gate.telemetry_context import ManagedTelemetrySession, TelemetryLifecycleError

# NOTE: rewritten against the actual ManagedTelemetrySession contract. The
# real class deliberately FORBIDS nested/concurrent re-entry (see its
# "Re-entrance Interlock" invariant in telemetry_context.py) -- this is the
# opposite of the originally-supplied version of this file, which assumed
# nested sessions were a supported, isolated-stack use case. That assumption
# does not hold against the built implementation, so these tests instead
# verify the interlock actually fires as designed.


def test_reentrant_entry_on_same_thread_is_rejected() -> None:
    """
    Control Invariant: Attempting to __enter__ an already-active
    ManagedTelemetrySession a second time on the same thread raises
    TelemetryLifecycleError ("Re-entrance Violation") rather than silently
    nesting or corrupting scheduler state.
    """
    sink = TransportTelemetrySink(capacity=50)
    session = ManagedTelemetrySession(
        telemetry_sink=sink,
        forwarder_fn=lambda batch: None,
        drain_interval_seconds=1.0,
        stop_timeout_seconds=1.0,
    )

    with session:
        assert session.is_active is True
        with pytest.raises(TelemetryLifecycleError, match="Re-entrance Violation"):
            with session:
                pass

    assert session.is_active is False


def test_concurrent_entry_from_another_thread_is_rejected() -> None:
    """
    Control Invariant: While a session is active on one thread, a second
    thread attempting to __enter__ the same session instance is rejected with
    TelemetryLifecycleError ("Concurrent Entry Violation"), preventing two
    threads from racing on the same scheduler lifecycle.
    """
    sink = TransportTelemetrySink(capacity=50)
    session = ManagedTelemetrySession(
        telemetry_sink=sink,
        forwarder_fn=lambda batch: None,
        drain_interval_seconds=1.0,
        stop_timeout_seconds=1.0,
    )
    errors: List[TelemetryLifecycleError] = []

    def enter_from_other_thread() -> None:
        try:
            with session:
                time.sleep(0.2)
        except TelemetryLifecycleError as e:
            errors.append(e)

    with session:
        t = threading.Thread(target=enter_from_other_thread)
        t.start()
        t.join(timeout=2.0)

    assert len(errors) == 1
    assert "Concurrent Entry Violation" in str(errors[0])
