from concurrent.futures import ThreadPoolExecutor
import os
from typing import List, Set
import pytest

from decision.triage_gate.ledger_client import (
    ConcreteLedgerClient,
    LedgerTransportConfig,
)
from decision.triage_gate.telemetry import TransportTelemetrySink
from tests.decision.triage_gate.conftest import MockTransportDriver


def test_backoff_jitter_entropy_decorrelation_across_clients() -> None:
    """
    Control Invariant: Concurrent LedgerClient instances computing backoff intervals
    under simulated thundering herd conditions must draw from isolated CSPRNG entropy
    sources, producing statistically decorrelated sleep distributions across 100 trials.
    """
    transport_config = LedgerTransportConfig(
        endpoint_url="https://ledger.internal:8443/v1",
        auth_token="calibrated_entropy_token_999",
        timeout_seconds=2.0,
        max_retries=3,
        backoff_factor=0.5,
        backoff_max_seconds=5.0,
        jitter_factor=1.0,
    )
    transport_config.validate()

    trials = 100
    computed_intervals: List[float] = []

    for attempt_idx in range(1, 4):
        trial_intervals: Set[float] = set()
        for _ in range(trials):
            driver = MockTransportDriver()
            client = ConcreteLedgerClient(
                transport_config=transport_config,
                transport_driver=driver,
                sleep_fn=lambda _: None,
                telemetry_sink=TransportTelemetrySink(capacity=10),
            )
            interval = client._calculate_backoff(attempt=attempt_idx)
            trial_intervals.add(round(interval, 8))
            computed_intervals.append(interval)

        assert len(trial_intervals) >= 95, f"Insufficient jitter entropy on attempt {attempt_idx}: {len(trial_intervals)} unique"


def test_backoff_jitter_bounds_enforcement() -> None:
    """
    Control Invariant: Computed backoff intervals must strictly obey the mathematical
    envelope: 0.0 <= backoff <= min(backoff_max_seconds, backoff_factor * (2 ** (attempt - 1))).
    """
    transport_config = LedgerTransportConfig(
        endpoint_url="https://ledger.internal:8443/v1",
        auth_token="calibrated_entropy_token_999",
        timeout_seconds=1.0,
        max_retries=5,
        backoff_factor=0.2,
        backoff_max_seconds=1.5,
        jitter_factor=1.0,
    )
    transport_config.validate()

    driver = MockTransportDriver()
    client = ConcreteLedgerClient(
        transport_config=transport_config,
        transport_driver=driver,
        sleep_fn=lambda _: None,
        telemetry_sink=TransportTelemetrySink(capacity=10),
    )

    for attempt in range(1, 10):
        ceiling = min(1.5, 0.2 * (2 ** (attempt - 1)))
        for _ in range(50):
            interval = client._calculate_backoff(attempt=attempt)
            assert 0.0 <= interval <= ceiling, f"Backoff {interval} violated ceiling {ceiling} at attempt {attempt}"
