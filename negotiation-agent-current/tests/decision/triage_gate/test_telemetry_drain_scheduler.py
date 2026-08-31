import threading
import time
from typing import Any, List
from unittest.mock import MagicMock
import pytest

from decision.triage_gate.telemetry import (
    TransportTelemetrySink,
    TelemetryDrainWorker,
)


def test_telemetry_drain_scheduler_periodic_flush_interval() -> None:
    """
    Control Invariant: TelemetryDrainWorker executes periodic timer-driven flushes
    when queued items are below batch_size threshold, ensuring low-volume telemetry
    is not stranded indefinitely in the sink buffer.
    """
    sink = TransportTelemetrySink(capacity=100)
    flush_timestamps: List[float] = []
    flushed_records: List[Any] = []
    lock = threading.Lock()

    def timestamped_handler(batch: List[Any]) -> None:
        with lock:
            flush_timestamps.append(time.time())
            flushed_records.extend(batch)

    worker = TelemetryDrainWorker(
        sink=sink,
        flush_handler=timestamped_handler,
        batch_size=50,
        flush_interval_seconds=0.05,
    )

    worker.start()

    for i in range(3):
        sink.record_event(
            event_type="HEARTBEAT",
            event_id=f"evt-sched-{i}",
            duration_ms=0.1,
            metadata={"tick": i},
        )

    time.sleep(0.12)
    worker.stop(timeout=1.0)

    with lock:
        assert len(flushed_records) == 3
        assert len(flush_timestamps) >= 1

    assert not worker.is_alive()


def test_telemetry_drain_scheduler_stop_flushes_remaining_buffer() -> None:
    """
    Control Invariant: Invoking stop() on TelemetryDrainWorker immediately triggers
    a final drain pass, ensuring in-flight events are fully committed before thread exit.
    """
    sink = TransportTelemetrySink(capacity=50)
    final_flushed: List[Any] = []

    worker = TelemetryDrainWorker(
        sink=sink,
        flush_handler=final_flushed.extend,
        batch_size=100,
        flush_interval_seconds=1.0,
    )

    worker.start()

    sink.record_event("SHUTDOWN_TRACE", "evt-term-01", 0.2)
    sink.record_event("SHUTDOWN_TRACE", "evt-term-02", 0.3)

    worker.stop(timeout=1.0)

    assert not worker.is_alive()
    assert len(final_flushed) == 2
    assert final_flushed[0]["event_id"] == "evt-term-01"
    assert final_flushed[1]["event_id"] == "evt-term-02"
