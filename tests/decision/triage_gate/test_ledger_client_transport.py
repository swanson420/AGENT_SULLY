from typing import Any, Mapping
from unittest.mock import MagicMock
import pytest

from decision.contracts.decision_package import (
    WorkingContext,
    DecisionRecord,
    RouteType,
    ActionType,
)
from decision.contracts.blast_radius import BlastRadiusScore
from decision.triage_gate.ledger_client import (
    ConcreteLedgerClient,
    LedgerTransportConfig,
    TransportConfigurationError,
    TransportExecutionError,
)
from decision.triage_gate.telemetry import TransportTelemetrySink


def test_transport_config_validation_rules() -> None:
    """
    Control Invariant: LedgerTransportConfig.validate() enforces strict boundaries
    on URL schemes, auth token entropy, timeouts, retries, and jitter factors.
    """
    with pytest.raises(TransportConfigurationError, match="Unsupported transport scheme"):
        cfg = LedgerTransportConfig(endpoint_url="ftp://ledger.local:8000", auth_token="valid_token_123")
        cfg.validate()

    with pytest.raises(TransportConfigurationError, match="fails minimum entropy threshold"):
        cfg = LedgerTransportConfig(endpoint_url="https://ledger.local:8000", auth_token="short")
        cfg.validate()

    with pytest.raises(TransportConfigurationError, match="Timeout .* out of acceptable bounds"):
        cfg = LedgerTransportConfig(endpoint_url="https://ledger.local:8000", auth_token="valid_token_123", timeout_seconds=0.0)
        cfg.validate()

    with pytest.raises(TransportConfigurationError, match="Max retries .* out of acceptable bounds"):
        cfg = LedgerTransportConfig(endpoint_url="https://ledger.local:8000", auth_token="valid_token_123", max_retries=10)
        cfg.validate()

    with pytest.raises(TransportConfigurationError, match="Jitter factor .* out of acceptable bounds"):
        cfg = LedgerTransportConfig(endpoint_url="https://ledger.local:8000", auth_token="valid_token_123", jitter_factor=1.5)
        cfg.validate()


def test_concrete_ledger_client_get_event_success(
    concrete_ledger_client: ConcreteLedgerClient,
    mock_driver: Any,
) -> None:
    """
    Control Invariant: get_event successfully queries the underlying transport driver
    and deserializes matching payload dictionaries.
    """
    mock_driver.seed_event("evt-trans-01", {"status": "ACTIVE", "code": 200})

    event = concrete_ledger_client.get_event("evt-trans-01")

    assert event is not None
    assert event["event_id"] == "evt-trans-01"
    assert event["payload"] == {"status": "ACTIVE", "code": 200}
    assert mock_driver.fetch_call_count == 1


def test_concrete_ledger_client_get_event_returns_none_on_driver_exhaustion(
    concrete_ledger_client: ConcreteLedgerClient,
    mock_driver: Any,
) -> None:
    """
    Control Invariant: When driver transport retries are exhausted under simulated
    network drop, get_event fails closed by returning None rather than crashing.
    """
    mock_driver.simulated_fault = ConnectionResetError("Connection refused by peer")

    event = concrete_ledger_client.get_event("evt-trans-02")

    assert event is None
    assert mock_driver.fetch_call_count == 3
    stats = concrete_ledger_client.telemetry.get_stats()
    assert stats["total_retries"] == 2
    assert stats["total_exhaustions"] == 1


def test_concrete_ledger_client_record_decision_view_posts_canonical_json(
    concrete_ledger_client: ConcreteLedgerClient,
    mock_driver: Any,
) -> None:
    """
    Control Invariant: record_decision_view validates the contract and posts
    canonically serialized JSON strings to the audit endpoint.
    """
    from datetime import datetime, timezone

    context = WorkingContext(
        source_event_ids=("evt-trans-01",),
        raw_payload={"sample": "data"},
        commitment_level="LOW",
        unknowns=(),
        assumptions=(),
    )
    record = DecisionRecord(
        route=RouteType.ACT_SILENTLY,
        action=ActionType.QUERY_INFO,
        context=context,
        blast_radius=BlastRadiusScore(
            reversibility="LOW",
            cost="LOW",
            relationship_impact="LOW",
            commitment="LOW",
            external_visibility="LOW",
        ),
        gate_results={"all_passed": True},
        audit_hash="f" * 64,
        timestamp=datetime.now(timezone.utc),
        rationale="Transport test record.",
    )

    success = concrete_ledger_client.record_decision_view(record)

    assert success is True
    assert mock_driver.post_call_count == 1
    assert len(mock_driver.audit_records) == 1
    assert '"audit_hash":"' + ("f" * 64) + '"' in mock_driver.audit_records[0]
