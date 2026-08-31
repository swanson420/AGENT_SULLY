from typing import Any
import pytest

from decision.triage_gate.ledger_client import (
    ConcreteLedgerClient,
    LedgerTransportConfig,
)
from tests.decision.triage_gate.conftest import MockTransportDriver


def test_mock_driver_reset_invariants_across_test_boundaries(mock_driver: MockTransportDriver) -> None:
    """
    Control Invariant: The MockTransportDriver fixture provides clean state isolation
    before and after execution, ensuring events, audit records, counters, and simulated
    faults are strictly purged without cross-test leakage.
    """
    assert len(mock_driver.events_db) == 0
    assert len(mock_driver.audit_records) == 0
    assert mock_driver.fetch_call_count == 0
    assert mock_driver.post_call_count == 0
    assert mock_driver.simulated_fault is None

    mock_driver.seed_event("evt-leak-check", {"field": "dirty_state"})
    mock_driver.post_audit_record("https://ledger.internal:8443/v1", "token", '{"audit": true}', 5.0)
    mock_driver.simulated_fault = RuntimeError("Transient disturbance")

    assert len(mock_driver.events_db) == 1
    assert len(mock_driver.audit_records) == 1
    assert mock_driver.post_call_count == 1
    assert mock_driver.simulated_fault is not None

    mock_driver.reset()

    assert len(mock_driver.events_db) == 0
    assert len(mock_driver.audit_records) == 0
    assert mock_driver.fetch_call_count == 0
    assert mock_driver.post_call_count == 0
    assert mock_driver.simulated_fault is None


def test_concrete_ledger_client_fixture_isolation(
    concrete_ledger_client: ConcreteLedgerClient,
    mock_driver: MockTransportDriver,
) -> None:
    """
    Control Invariant: ConcreteLedgerClient fixture operates on a hermetic driver
    instance and isolated telemetry sink per test run.
    """
    assert mock_driver.fetch_call_count == 0
    stats = concrete_ledger_client.telemetry.get_stats()
    assert stats["total_retries"] == 0
    assert stats["total_exhaustions"] == 0

    mock_driver.seed_event("evt-fixture-01", {"status": "ISOLATED"})
    event = concrete_ledger_client.get_event("evt-fixture-01")

    assert event is not None
    assert event["event_id"] == "evt-fixture-01"
    assert mock_driver.fetch_call_count == 1
