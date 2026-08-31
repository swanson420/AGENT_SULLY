import json
from typing import Any
import pytest

from decision.contracts.decision_package import (
    WorkingContext,
    DecisionRecord,
    RouteType,
    ActionType,
    Assumption,
)
from decision.contracts.blast_radius import BlastRadiusScore
from decision.triage_gate.config import DEFAULT_CONFIG
from decision.triage_gate.provenance import ProvenanceEngine
from decision.triage_gate.triage import TriagePipelineOrchestrator


def test_concrete_harness_e2e_serialization_roundtrip(
    standard_orchestrator: TriagePipelineOrchestrator,
    mock_driver: Any,
) -> None:
    """
    Control Invariant: Proves end-to-end execution across the concrete harness,
    verifying that the audit stage serializes the complete DecisionRecord into
    valid, un-truncated JSON bytes matching the ledger commit contract.
    """
    payload = {
        "cluster_op": "REBALANCE_NODES",
        "target_nodes": ["node-01", "node-02", "node-03"],
        "parameters": {"evacuate_timeout": 300},
        "blast_radius": {
            "reversibility": "LOW",
            "cost": "LOW",
            "relationship_impact": "LOW",
            "commitment": "LOW",
            "external_visibility": "LOW",
        },
    }

    mock_driver.seed_event("evt-harness-e2e-01", payload)

    context = WorkingContext(
        source_event_ids=("evt-harness-e2e-01",),
        raw_payload=payload,
        commitment_level="LOW",
        unknowns=(),
        assumptions=(
            Assumption(
                description="Cluster health status is GREEN",
                confidence=0.98,
                grounded=True,
            ),
        ),
    )

    route, record = standard_orchestrator.execute(
        context=context,
        proposed_action=ActionType.EXECUTE_QUERY,
    )

    assert route == RouteType.ACT_SILENTLY
    assert record.route == RouteType.ACT_SILENTLY
    assert record.action == ActionType.EXECUTE_QUERY
    assert all(record.gate_results.values()) is True

    assert len(mock_driver.audit_records) == 1
    raw_posted_json = mock_driver.audit_records[0]
    deserialized_audit = json.loads(raw_posted_json)

    assert deserialized_audit["route"] == "ACT_SILENTLY"
    assert deserialized_audit["action"] == "EXECUTE_QUERY"
    assert deserialized_audit["audit_hash"] == record.audit_hash
    assert deserialized_audit["blast_radius"]["reversibility"] == "LOW"
    assert deserialized_audit["blast_radius"]["commitment"] == "LOW"
    assert deserialized_audit["gate_results"]["ledger_anchored"] is True
    assert deserialized_audit["gate_results"]["interpretation_stable"] is True
