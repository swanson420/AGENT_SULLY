from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from typing import List, Set
import pytest

from decision.triage_gate.ledger_client import (
    ConcreteLedgerClient,
    LedgerTransportConfig,
)
from decision.triage_gate.telemetry import TransportTelemetrySink
from tests.decision.triage_gate.conftest import MockTransportDriver


def test_high_concurrency_entropy_burst_decorrelation() -> None:
    """
    Control Invariant: 64 concurrent worker threads firing simultaneous retry backoffs
    must generate mutually decorrelated jitter values without mutex lock contention,
    entropy collapse, or duplicate collision cascades.
    """
    transport_config = LedgerTransportConfig(
        endpoint_url="https://ledger.internal:8443/v1",
        auth_token="calibrated_entropy_token_999",
        timeout_seconds=3.0,
        max_retries=3,
        backoff_factor=0.5,
        backoff_max_seconds=5.0,
        jitter_factor=1.0,
    )
    transport_config.validate()

    barrier = threading.Barrier(parties=64)
    results: List[float] = []

    def concurrent_jitter_worker(worker_id: int) -> float:
        driver = MockTransportDriver()
        client = ConcreteLedgerClient(
            transport_config=transport_config,
            transport_driver=driver,
            sleep_fn=lambda _: None,
            telemetry_sink=TransportTelemetrySink(capacity=10),
        )
        barrier.wait(timeout=5.0)
        return client._calculate_backoff(attempt=2)

    with ThreadPoolExecutor(max_workers=64) as executor:
        futures = [executor.submit(concurrent_jitter_worker, i) for i in range(64)]
        for f in as_completed(futures):
            results.append(f.result())

    assert len(results) == 64

    unique_values: Set[float] = set(results)
    assert len(unique_values) == 64, (
        f"Entropy collision detected under concurrent burst: {64 - len(unique_values)} duplicates found."
    )

    for val in results:
        assert 0.0 <= val <= 1.0
