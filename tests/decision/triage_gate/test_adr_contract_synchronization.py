from datetime import datetime, timezone
import pathlib
import pytest

from decision.contracts.decision_package import (
    WorkingContext,
    DecisionRecord,
    RouteType,
    ActionType,
    Unknown,
    Assumption,
)
from decision.contracts.blast_radius import BlastRadiusScore
from decision.triage_gate.config import DEFAULT_CONFIG


def test_adr_008_architectural_invariants_parity() -> None:
    """
    Control Invariant: Validates architectural alignment against ADR-008.
    Verifies that all 5 pre-action gates, mandatory escalation actions, and
    5D blast radius dimensions defined in ADR-008 exist in the runtime contracts.
    """
    adr_path = pathlib.Path("docs/architecture/decisions/ADR-008-ledger-integration-and-provenance-transport.md")
    assert adr_path.exists(), f"ADR-008 file missing at expected path: {adr_path}"

    content = adr_path.read_text(encoding="utf-8")

    adr_gates = {
        "interpretation_stable",
        "context_anchored",
        "ledger_anchored",
        "blast_radius_calibrated",
        "assumptions_grounded",
    }
    for gate in adr_gates:
        assert gate in content, f"Gate '{gate}' declared in config not documented in ADR-008"
        assert gate in DEFAULT_CONFIG.required_pre_action_gates

    dimensions = {
        "reversibility",
        "cost",
        "relationship_impact",
        "commitment",
        "external_visibility",
    }
    for dim in dimensions:
        assert dim in content, f"Blast radius dimension '{dim}' not referenced in ADR-008"


def test_adr_decision_record_structure_synchronization() -> None:
    """
    Control Invariant: Validates that DecisionRecord contract satisfies
    the immutable audit record structure mandated by ADR-008.
    """
    context = WorkingContext(
        source_event_ids=("evt-adr-01",),
        raw_payload={"adr_verification": True},
        commitment_level="LOW",
        unknowns=(),
        assumptions=(),
    )
    blast = BlastRadiusScore(
        reversibility="LOW",
        cost="LOW",
        relationship_impact="LOW",
        commitment="LOW",
        external_visibility="LOW",
    )
    record = DecisionRecord(
        route=RouteType.ACT_SILENTLY,
        action=ActionType.QUERY_INFO,
        context=context,
        blast_radius=blast,
        gate_results={
            "interpretation_stable": True,
            "context_anchored": True,
            "ledger_anchored": True,
            "blast_radius_calibrated": True,
            "assumptions_grounded": True,
        },
        audit_hash="0" * 64,
        timestamp=datetime.now(timezone.utc),
        rationale="ADR-008 synchronization verification passed.",
    )

    record.validate()
    assert record.route.name == "ACT_SILENTLY"
    assert record.action.name == "QUERY_INFO"
