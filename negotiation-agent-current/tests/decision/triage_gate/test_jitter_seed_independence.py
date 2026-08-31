import os
import random
from typing import Set
import pytest

from decision.triage_gate.ledger_client import (
    ConcreteLedgerClient,
    LedgerTransportConfig,
)
from decision.triage_gate.telemetry import TransportTelemetrySink
from tests.decision.triage_gate.conftest import MockTransportDriver


def test_jitter_seed_independence_from_global_random_state() -> None:
    """
    Control Invariant: ConcreteLedgerClient's jitter generator must utilize
    an independent, isolated entropy source (e.g. os.urandom or a dedicated CSPRNG instance)
    so that caller-side seeding of Python's global `random.seed()` does not synchronize,
    freeze, or make predictable the backoff jitter across different client instances.
    """
    transport_config = LedgerTransportConfig(
        endpoint_url="https://ledger.internal:8443/v1",
        auth_token="entropy_token_calibrated_777",
        timeout_seconds=2.0,
        max_retries=3,
        backoff_factor=0.2,
        backoff_max_seconds=2.0,
        jitter_factor=1.0,
    )
    transport_config.validate()

    driver = MockTransportDriver()
    telemetry = TransportTelemetrySink(capacity=10)

    random.seed(42)
    client_a = ConcreteLedgerClient(
        transport_config=transport_config,
        transport_driver=driver,
        sleep_fn=lambda _: None,
        telemetry_sink=telemetry,
    )
    backoff_a_1 = client_a._calculate_backoff(attempt=1)
    backoff_a_2 = client_a._calculate_backoff(attempt=2)

    random.seed(42)
    client_b = ConcreteLedgerClient(
        transport_config=transport_config,
        transport_driver=driver,
        sleep_fn=lambda _: None,
        telemetry_sink=telemetry,
    )
    backoff_b_1 = client_b._calculate_backoff(attempt=1)
    backoff_b_2 = client_b._calculate_backoff(attempt=2)

    assert backoff_a_1 != backoff_b_1 or backoff_a_2 != backoff_b_2, (
        "Client backoff jitter locked to global random.seed() state! Jitter must be independent."
    )


def test_consecutive_backoff_evaluations_produce_distinct_values() -> None:
    """
    Control Invariant: Evaluating backoff jitter repeatedly on the same client instance
    produces a continuous distribution of values without state stagnation.
    """
    transport_config = LedgerTransportConfig(
        endpoint_url="https://ledger.internal:8443/v1",
        auth_token="entropy_token_calibrated_777",
        timeout_seconds=1.0,
        max_retries=4,
        backoff_factor=0.1,
        backoff_max_seconds=1.0,
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

    distinct_evaluations: Set[float] = {
        client._calculate_backoff(attempt=2) for _ in range(50)
    }

    assert len(distinct_evaluations) >= 45
