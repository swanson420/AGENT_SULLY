from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock
import pytest

from decision.contracts.decision_package import (
    WorkingContext,
    DecisionRecord,
    RouteType,
    ActionType,
    Assumption,
)
from decision.contracts.blast_radius import BlastRadiusScore
from decision.triage_gate.provenance import ProvenanceEngine
from decision.triage_gate.triage import TriagePipelineOrchestrator


def test_orchestrator_integration_with_concrete_ledger_client_nominal(
    standard_orchestrator: TriagePipelineOrchestrator,
    mock_driver: Any,
) -> None:
    """
    Control Invariant: Full end-to-end pipeline execution with ConcreteLedgerClient
    verifies cryptographic provenance, gates nominal conditions, and writes
    the audited view to the remote driver.
    """
    payload = {
        "service": "indexing_worker",
        "action": "QUERY_REINDEX_STATUS",
        "blast_radius": {
            "reversibility": "LOW",
            "cost": "LOW",
            "relationship_impact": "LOW",
            "commitment": "LOW",
            "external_visibility": "LOW",
        },
    }

    mock_driver.seed_event("evt-int-01", payload)

    context = WorkingContext(
        source_event_ids=("evt-int-01",),
        raw_payload=payload,
        commitment_level="LOW",
        unknowns=(),
        assumptions=(
            Assumption(
                description="Worker queue active",
                confidence=0.99,
                grounded=True,
            ),
        ),
    )

    route, record = standard_orchestrator.execute(
        context=context,
        proposed_action=ActionType.QUERY_INFO,
    )

    assert route == RouteType.ACT_SILENTLY
    assert record.route == RouteType.ACT_SILENTLY
    assert record.gate_results["ledger_anchored"] is True
    assert len(mock_driver.audit_records) == 1
    assert mock_driver.post_call_count == 1


def test_orchestrator_integration_fails_closed_when_driver_outage_occurs(
    standard_orchestrator: TriagePipelineOrchestrator,
    mock_driver: Any,
) -> None:
    """
    Control Invariant: Total network driver outage causes provenance fetch to fail,
    tripping the ledger_anchored gate and forcing fail-closed BOUNCE_META_ESCALATED.
    """
    payload = {
        "service": "indexing_worker",
        "blast_radius": {
            "reversibility": "LOW",
            "cost": "LOW",
            "relationship_impact": "LOW",
            "commitment": "LOW",
            "external_visibility": "LOW",
        },
    }

    mock_driver.seed_event("evt-int-02", payload)
    mock_driver.simulated_fault = TimeoutError("Connection to ledger timed out")

    context = WorkingContext(
        source_event_ids=("evt-int-02",),
        raw_payload=payload,
        commitment_level="LOW",
        unknowns=(),
        assumptions=(),
    )

    route, record = standard_orchestrator.execute(
        context=context,
        proposed_action=ActionType.QUERY_INFO,
    )

    assert route == RouteType.BOUNCE_META_ESCALATED
    assert record.route == RouteType.BOUNCE_META_ESCALATED
    assert record.gate_results["ledger_anchored"] is False
    assert "Ledger provenance verification failed" in record.rationale
