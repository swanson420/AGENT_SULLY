import hashlib
from typing import Any, Dict
import pytest

from decision.contracts.decision_package import (
    WorkingContext,
    DecisionRecord,
    RouteType,
    ActionType,
)
from decision.contracts.blast_radius import BlastRadiusScore
from decision.triage_gate.provenance import ProvenanceEngine
from decision.triage_gate.triage import TriagePipelineOrchestrator


def test_orchestrator_fails_closed_on_tampered_payload(
    standard_orchestrator: TriagePipelineOrchestrator,
    mock_driver: Any,
) -> None:
    """
    Control Invariant: If a caller tampers with the raw payload after anchoring
    in the ledger, the provenance digest check in Stage 4 fails closed to
    BOUNCE_META_ESCALATED, denying ACT_SILENTLY.
    """
    original_payload = {
        "action": "CONFIG_UPDATE",
        "value": 100,
        "blast_radius": {
            "reversibility": "LOW",
            "cost": "LOW",
            "relationship_impact": "LOW",
            "commitment": "LOW",
            "external_visibility": "LOW",
        },
    }

    mock_driver.seed_event("evt-adv-01", original_payload)

    tampered_payload = {
        "action": "CONFIG_UPDATE",
        "value": 999999,
        "blast_radius": {
            "reversibility": "LOW",
            "cost": "LOW",
            "relationship_impact": "LOW",
            "commitment": "LOW",
            "external_visibility": "LOW",
        },
    }

    context = WorkingContext(
        source_event_ids=("evt-adv-01",),
        raw_payload=tampered_payload,
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
    assert len(mock_driver.audit_records) == 1


def test_orchestrator_fails_closed_on_forged_event_id(
    standard_orchestrator: TriagePipelineOrchestrator,
    mock_driver: Any,
) -> None:
    """
    Control Invariant: Submitting a forged or non-existent event ID prevents
    ledger anchor verification and fails closed to BOUNCE_META_ESCALATED.
    """
    payload = {
        "action": "SAFE_PROBE",
        "blast_radius": {
            "reversibility": "LOW",
            "cost": "LOW",
            "relationship_impact": "LOW",
            "commitment": "LOW",
            "external_visibility": "LOW",
        },
    }

    context = WorkingContext(
        source_event_ids=("evt-forged-99",),
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
    assert record.gate_results["ledger_anchored"] is False
    assert "Ledger provenance verification failed" in record.rationale


def test_orchestrator_fails_closed_on_empty_source_events(
    standard_orchestrator: TriagePipelineOrchestrator,
) -> None:
    """
    Control Invariant: Contexts with zero source event IDs fail both
    context_anchored and ledger_anchored gates, enforcing BOUNCE_META_ESCALATED.
    """
    payload = {"unanchored": "data"}

    context = WorkingContext(
        source_event_ids=(),
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
    assert record.gate_results["context_anchored"] is False
    assert record.gate_results["ledger_anchored"] is False
