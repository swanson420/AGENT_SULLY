import time
from typing import Any, List
from unittest.mock import MagicMock
import pytest

from decision.contracts.decision_package import (
    WorkingContext,
    DecisionRecord,
    RouteType,
    ActionType,
)
from decision.contracts.blast_radius import BlastRadiusScore
from decision.triage_gate.config import DEFAULT_CONFIG
from decision.triage_gate.ledger_client import (
    ConcreteLedgerClient,
    LedgerTransportConfig,
)
from decision.triage_gate.provenance import ProvenanceEngine
from decision.triage_gate.telemetry import TransportTelemetrySink
from decision.triage_gate.triage import TriagePipelineOrchestrator
from tests.decision.triage_gate.conftest import MockTransportDriver


def test_pipeline_execution_under_transport_retry_delays() -> None:
    """
    Control Invariant: When the underlying transport encounters transient drops,
    the pipeline orchestrator gracefully absorbs the backoff intervals, preserves
    end-to-end evaluation determinism, and logs latency telemetry without dropping
    audit fidelity.
    """
    mock_driver = MockTransportDriver()
    payload = {
        "operation": "BATCH_FLUSH",
        "blast_radius": {
            "reversibility": "LOW",
            "cost": "LOW",
            "relationship_impact": "LOW",
            "commitment": "LOW",
            "external_visibility": "LOW",
        },
    }

    mock_driver.seed_event("evt-latency-01", payload)

    backoff_intervals: List[float] = []

    def tracking_sleep(seconds: float) -> None:
        backoff_intervals.append(seconds)

    attempt_count = [0]
    original_fetch = mock_driver.fetch_event

    def flaky_fetch(endpoint: str, token: str, event_id: str, timeout: float):
        attempt_count[0] += 1
        if attempt_count[0] == 1:
            raise ConnectionResetError("Transient socket disconnect")
        return original_fetch(endpoint, token, event_id, timeout)

    mock_driver.fetch_event = flaky_fetch  # type: ignore[assignment]

    transport_config = LedgerTransportConfig(
        endpoint_url="https://ledger.internal:8443/v1",
        auth_token="calibrated_entropy_token_999",
        timeout_seconds=2.0,
        max_retries=2,
        backoff_factor=0.05,
        backoff_max_seconds=0.5,
        jitter_factor=1.0,
    )
    transport_config.validate()

    telemetry_sink = TransportTelemetrySink(capacity=100)
    client = ConcreteLedgerClient(
        transport_config=transport_config,
        transport_driver=mock_driver,
        sleep_fn=tracking_sleep,
        telemetry_sink=telemetry_sink,
    )

    from decision.triage_gate.stages.stage1_surfacing import StrictUnknownSurfacingStage
    from decision.triage_gate.stages.stage2_resolvability import StrictResolvabilityStage
    from decision.triage_gate.stages.stage3_blast_radius import StrictBlastRadiusStage
    from decision.triage_gate.stages.stage4_routing import StrictRoutingStage
    from decision.triage_gate.stages.stage5_audit import StrictAuditStage

    config = DEFAULT_CONFIG
    orchestrator = TriagePipelineOrchestrator(
        surfacing_stage=StrictUnknownSurfacingStage(),
        resolvability_stage=StrictResolvabilityStage(),
        blast_radius_stage=StrictBlastRadiusStage(config),
        routing_stage=StrictRoutingStage(config),
        audit_stage=StrictAuditStage(),
        ledger=client,
        config=config,
    )

    context = WorkingContext(
        source_event_ids=("evt-latency-01",),
        raw_payload=payload,
        commitment_level="LOW",
        unknowns=(),
        assumptions=(),
    )

    route, record = orchestrator.execute(context, ActionType.QUERY_INFO)

    assert route == RouteType.ACT_SILENTLY
    assert record.route == RouteType.ACT_SILENTLY
    assert record.gate_results["ledger_anchored"] is True

    assert attempt_count[0] == 2
    assert len(backoff_intervals) == 1
    assert 0.0 <= backoff_intervals[0] <= 0.5

    stats = telemetry_sink.get_stats()
    assert stats["total_retries"] == 1
    assert stats["total_exhaustions"] == 0
    assert len(mock_driver.audit_records) == 1
