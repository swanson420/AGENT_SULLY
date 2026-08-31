from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from typing import List
import pytest

from decision.triage_gate.telemetry import (
    TransportTelemetrySink,
    ManagedTelemetrySession,
)


def test_high_concurrency_telemetry_throughput_and_thread_safety() -> None:
    """
    Control Invariant: The TransportTelemetrySink must maintain thread-safe,
    non-blocking operation under concurrent writes from 64 worker threads.
    Atomic metrics counters and the bounded ring buffer must never deadlock,
    drop events out-of-order, or raise race condition exceptions.
    """
    capacity = 1000
    sink = TransportTelemetrySink(capacity=capacity)
    barrier = threading.Barrier(parties=64)
    iterations_per_worker = 50

    def telemetry_writer_worker(worker_id: int) -> int:
        barrier.wait(timeout=5.0)
        emitted_count = 0
        for i in range(iterations_per_worker):
            sink.record_event(
                event_type="RETRY_ATTEMPT",
                event_id=f"evt-burst-{worker_id}-{i}",
                duration_ms=1.25 + (i * 0.01),
                metadata={"worker": worker_id, "iteration": i},
            )
            emitted_count += 1
        return emitted_count

    with ThreadPoolExecutor(max_workers=64) as executor:
        futures = [executor.submit(telemetry_writer_worker, wid) for wid in range(64)]
        total_emitted = sum(f.result() for f in as_completed(futures))

    assert total_emitted == 64 * iterations_per_worker

    stats = sink.get_stats()
    assert stats["total_retries"] == total_emitted
    assert stats["total_exhaustions"] == 0
    assert stats["dropped_logs"] == total_emitted - capacity
    assert len(sink.get_recent_events()) == capacity


def test_managed_telemetry_session_context_management_under_concurrency() -> None:
    """
    Control Invariant: ManagedTelemetrySession accurately measures and flushes
    telemetry event contexts under concurrent execution scopes without cross-thread
    state contamination.
    """
    sink = TransportTelemetrySink(capacity=200)
    worker_count = 16

    def session_worker(worker_id: int) -> None:
        with ManagedTelemetrySession(sink=sink, session_name=f"session-{worker_id}") as session:
            session.record_step("INITIALIZE", status="OK")
            session.record_step("DISPATCH", status="SUCCESS")

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(session_worker, wid) for wid in range(worker_count)]
        for f in as_completed(futures):
            f.result()

    events = sink.get_recent_events()
    assert len(events) == worker_count * 2

    session_names = {e["metadata"]["session_name"] for e in events if "session_name" in e.get("metadata", {})}
    expected_sessions = {f"session-{i}" for i in range(worker_count)}
    assert session_names == expected_sessions
