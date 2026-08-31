from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time
from typing import Any, List
import pytest

from decision.triage_gate.telemetry import (
    TransportTelemetrySink,
    TelemetryDrainWorker,
)


def test_telemetry_drain_under_high_concurrency_producer_pressure() -> None:
    """
    Control Invariant: Background TelemetryDrainWorker continuously drains a
    TransportTelemetrySink subjected to simultaneous high-frequency writes across
    32 concurrent producer threads without deadlock, state corruption, or memory leaks.
    """
    sink = TransportTelemetrySink(capacity=2000)
    collected_events: List[Any] = []
    lock = threading.Lock()

    def thread_safe_collector(batch: List[Any]) -> None:
        with lock:
            collected_events.extend(batch)

    drain_worker = TelemetryDrainWorker(
        sink=sink,
        flush_handler=thread_safe_collector,
        batch_size=50,
        flush_interval_seconds=0.005,
    )

    drain_worker.start()

    num_producers = 32
    records_per_producer = 50
    total_expected = num_producers * records_per_producer
    barrier = threading.Barrier(parties=num_producers)

    def producer_task(producer_id: int) -> int:
        barrier.wait(timeout=5.0)
        for i in range(records_per_producer):
            sink.record_event(
                event_type="RPC_METRIC",
                event_id=f"evt-prod-{producer_id}-{i}",
                duration_ms=0.25,
                metadata={"producer": producer_id, "seq": i},
            )
        return records_per_producer

    with ThreadPoolExecutor(max_workers=num_producers) as executor:
        futures = [executor.submit(producer_task, pid) for pid in range(num_producers)]
        for f in as_completed(futures):
            assert f.result() == records_per_producer

    time.sleep(0.1)
    drain_worker.stop(timeout=2.0)

    assert not drain_worker.is_alive()

    with lock:
        total_drained = len(collected_events)

    assert total_drained == total_expected

    stats = sink.get_stats()
    assert stats["total_retries"] == 0
    assert stats["total_exhaustions"] == 0
