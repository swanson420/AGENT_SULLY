from typing import Any
import pytest

from decision.contracts.decision_package import (
    WorkingContext,
    RouteType,
    ActionType,
)
from decision.triage_gate.ledger_client import ConcreteLedgerClient
from decision.triage_gate.triage import TriagePipelineOrchestrator
from tests.decision.triage_gate.test_mock_ledger import MockLedger


def test_fixture_isolation_and_coexistence_with_mock_ledger(
    standard_orchestrator: TriagePipelineOrchestrator,
    concrete_ledger_client: ConcreteLedgerClient,
    mock_driver: Any,
) -> None:
    """
    Control Invariant: Verifies that global concrete fixtures coexist cleanly
    alongside local hermetic mock fixtures without state clobbering, telemetry bleed,
    or driver pollution across test execution boundaries.
    """
    local_mock = MockLedger()
    local_payload = {"isolated_scope": "local_mock_run"}
    local_mock.record_event("evt-local-01", local_payload)

    concrete_payload = {"isolated_scope": "concrete_driver_run"}
    mock_driver.seed_event("evt-concrete-01", concrete_payload)

    assert "evt-local-01" not in mock_driver.events_db
    assert "evt-concrete-01" not in local_mock._events

    concrete_event = concrete_ledger_client.get_event("evt-concrete-01")
    assert concrete_event is not None
    assert concrete_event["payload"] == concrete_payload

    mock_event = local_mock.get_event("evt-local-01")
    assert mock_event is not None
    assert mock_event["payload"] == local_payload

    stats = concrete_ledger_client.telemetry.get_stats()
    assert stats["total_retries"] == 0
    assert stats["total_exhaustions"] == 0
    assert stats["dropped_logs"] == 0
