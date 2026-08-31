import time
from typing import Any, List
from unittest.mock import MagicMock
import pytest

from decision.triage_gate.telemetry import (
    TransportTelemetrySink,
    TelemetryDrainWorker,
)


def test_telemetry_drain_worker_lifecycle_and_batch_flush() -> None:
    """
    Control Invariant: TelemetryDrainWorker continuously drains queued telemetry
    events from TransportTelemetrySink in deterministic batch slices, invokes
    the external dispatch handler, and shuts down cleanly on stop signal.
    """
    sink = TransportTelemetrySink(capacity=100)
    flushed_batches: List[List[Any]] = []

    def mock_flush_handler(batch: List[Any]) -> None:
        flushed_batches.append(list(batch))

    worker = TelemetryDrainWorker(
        sink=sink,
        flush_handler=mock_flush_handler,
        batch_size=10,
        flush_interval_seconds=0.01,
    )

    for i in range(25):
        sink.record_event(
            event_type="TRANSPORT_DISPATCH",
            event_id=f"evt-drain-{i}",
            duration_ms=0.5,
            metadata={"seq": i},
        )

    worker.start()
    time.sleep(0.05)
    worker.stop(timeout=1.0)

    assert not worker.is_alive()

    total_drained = sum(len(b) for b in flushed_batches)
    assert total_drained == 25
    assert len(flushed_batches) >= 3

    first_event = flushed_batches[0][0]
    assert first_event["event_id"] == "evt-drain-0"
    last_batch = flushed_batches[-1]
    assert last_batch[-1]["event_id"] == "evt-drain-24"


def test_telemetry_drain_worker_handles_handler_exception_gracefully() -> None:
    """
    Control Invariant: An unhandled exception inside the downstream flush handler
    does not crash the worker thread; the worker logs the fault, preserves internal
    loop stability, and continues draining subsequent batches.
    """
    sink = TransportTelemetrySink(capacity=50)
    fault_counter = [0]
    successful_events: List[Any] = []

    def unstable_handler(batch: List[Any]) -> None:
        fault_counter[0] += 1
        if fault_counter[0] == 1:
            raise ConnectionError("Downstream telemetry collector unreachable")
        successful_events.extend(batch)

    worker = TelemetryDrainWorker(
        sink=sink,
        flush_handler=unstable_handler,
        batch_size=5,
        flush_interval_seconds=0.01,
    )

    for i in range(10):
        sink.record_event(
            event_type="RETRY_BACKOFF",
            event_id=f"evt-fault-{i}",
            duration_ms=1.0,
            metadata={"idx": i},
        )

    worker.start()
    time.sleep(0.05)
    worker.stop(timeout=1.0)

    assert fault_counter[0] >= 1
    assert len(successful_events) > 0
    assert not worker.is_alive()
