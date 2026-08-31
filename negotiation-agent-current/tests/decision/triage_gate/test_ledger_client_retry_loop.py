from typing import Any, List
import pytest

from decision.triage_gate.ledger_client import (
    ConcreteLedgerClient,
    LedgerTransportConfig,
)
from decision.triage_gate.telemetry import TransportTelemetrySink
from tests.decision.triage_gate.conftest import MockTransportDriver


def test_retry_loop_recovers_after_transient_failures() -> None:
    """
    Control Invariant: When the transport driver throws transient connection errors,
    ConcreteLedgerClient executes exponential backoff with full jitter, recovering
    cleanly if a subsequent attempt succeeds within max_retries bounds.
    """
    driver = MockTransportDriver()
    driver.seed_event("evt-retry-01", {"state": "RECOVERED"})

    sleep_durations: List[float] = []

    def mock_sleep(seconds: float) -> None:
        sleep_durations.append(seconds)

    config = LedgerTransportConfig(
        endpoint_url="https://ledger.internal:8443/v1",
        auth_token="entropy_token_valid_1234",
        timeout_seconds=2.0,
        max_retries=3,
        backoff_factor=0.2,
        backoff_max_seconds=2.0,
        jitter_factor=1.0,
    )
    config.validate()

    telemetry = TransportTelemetrySink(capacity=50)

    original_fetch = driver.fetch_event
    attempt_counter = [0]

    def flaky_fetch(endpoint: str, token: str, event_id: str, timeout: float):
        attempt_counter[0] += 1
        if attempt_counter[0] <= 2:
            raise ConnectionResetError("Transient network drop")
        return original_fetch(endpoint, token, event_id, timeout)

    driver.fetch_event = flaky_fetch  # type: ignore[assignment]

    client = ConcreteLedgerClient(
        transport_config=config,
        transport_driver=driver,
        sleep_fn=mock_sleep,
        telemetry_sink=telemetry,
    )

    event = client.get_event("evt-retry-01")

    assert event is not None
    assert event["payload"] == {"state": "RECOVERED"}
    assert attempt_counter[0] == 3
    assert len(sleep_durations) == 2

    for d in sleep_durations:
        assert 0.0 <= d <= 2.0

    stats = telemetry.get_stats()
    assert stats["total_retries"] == 2
    assert stats["total_exhaustions"] == 0


def test_retry_loop_exhaustion_increments_telemetry_counters() -> None:
    """
    Control Invariant: Complete retry exhaustion under continuous network failure
    records exact retry counts and exhaustion metrics in telemetry without raising.
    """
    driver = MockTransportDriver()
    driver.simulated_fault = TimeoutError("Network endpoint unreachable")

    config = LedgerTransportConfig(
        endpoint_url="https://ledger.internal:8443/v1",
        auth_token="entropy_token_valid_1234",
        timeout_seconds=1.0,
        max_retries=2,
        backoff_factor=0.05,
        backoff_max_seconds=0.5,
        jitter_factor=1.0,
    )
    config.validate()

    telemetry = TransportTelemetrySink(capacity=50)

    client = ConcreteLedgerClient(
        transport_config=config,
        transport_driver=driver,
        sleep_fn=lambda _: None,
        telemetry_sink=telemetry,
    )

    event = client.get_event("evt-exhaust-01")

    assert event is None
    assert driver.fetch_call_count == 3

    stats = telemetry.get_stats()
    assert stats["total_retries"] == 2
    assert stats["total_exhaustions"] == 1
