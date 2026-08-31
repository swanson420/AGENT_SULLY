from datetime import datetime, timezone
from typing import Any
import pytest

from decision.contracts.decision_package import (
    WorkingContext,
    DecisionRecord,
    RouteType,
    ActionType,
    Assumption,
    Unknown,
)
from decision.contracts.blast_radius import BlastRadiusScore
from decision.triage_gate.config import DEFAULT_CONFIG
from decision.triage_gate.provenance import ProvenanceEngine
from decision.triage_gate.triage import TriagePipelineOrchestrator


def test_e2e_isolated_pipeline_domain_bounce(
    standard_orchestrator: TriagePipelineOrchestrator,
    mock_driver: Any,
) -> None:
    """
    Control Invariant: An ungrounded assumption (< 0.70 confidence) or unresolved
    critical unknown forces trajectory diversion to BOUNCE_DOMAIN.
    """
    payload = {
        "operation": "PROVISION_REPLICA",
        "blast_radius": {
            "reversibility": "LOW",
            "cost": "LOW",
            "relationship_impact": "LOW",
            "commitment": "LOW",
            "external_visibility": "LOW",
        },
    }

    mock_driver.seed_event("evt-e2e-01", payload)

    context = WorkingContext(
        source_event_ids=("evt-e2e-01",),
        raw_payload=payload,
        commitment_level="LOW",
        unknowns=(
            Unknown(
                description="Cluster subnet CIDR allocation unknown",
                criticality="HIGH",
                resolution_precedent=None,
            ),
        ),
        assumptions=(
            Assumption(
                description="Capacity available in target AZ",
                confidence=0.50,
                grounded=False,
            ),
        ),
    )

    route, record = standard_orchestrator.execute(
        context=context,
        proposed_action=ActionType.QUERY_INFO,
    )

    assert route == RouteType.BOUNCE_DOMAIN
    assert record.route == RouteType.BOUNCE_DOMAIN
    assert record.gate_results["interpretation_stable"] is False
    assert record.gate_results["assumptions_grounded"] is False
    assert record.gate_results["ledger_anchored"] is True
    assert "Domain clarification required" in record.rationale
    assert len(mock_driver.audit_records) == 1


def test_e2e_isolated_pipeline_meta_escalation_on_high_blast(
    standard_orchestrator: TriagePipelineOrchestrator,
    mock_driver: Any,
) -> None:
    """
    Control Invariant: When blast radius contains CRITICAL dimensions,
    trajectory fails closed to BOUNCE_META_ESCALATED.
    """
    payload = {
        "operation": "DROP_PRIMARY_INDEX",
        "blast_radius": {
            "reversibility": "CRITICAL",
            "cost": "HIGH",
            "relationship_impact": "CRITICAL",
            "commitment": "HIGH",
            "external_visibility": "MEDIUM",
        },
    }

    mock_driver.seed_event("evt-e2e-02", payload)

    context = WorkingContext(
        source_event_ids=("evt-e2e-02",),
        raw_payload=payload,
        commitment_level="HIGH",
        unknowns=(),
        assumptions=(),
    )

    route, record = standard_orchestrator.execute(
        context=context,
        proposed_action=ActionType.MUTATE_STATE,
    )

    assert route == RouteType.BOUNCE_META_ESCALATED
    assert record.route == RouteType.BOUNCE_META_ESCALATED
    assert record.gate_results["blast_radius_calibrated"] is False
    assert "Blast radius exceeds acceptable operational threshold" in record.rationale
    assert len(mock_driver.audit_records) == 1
