import pytest

from decision.contracts.decision_package import (
    WorkingContext,
    ActionType,
)
from decision.contracts.blast_radius import BlastRadiusScore
from decision.triage_gate.config import DEFAULT_CONFIG, TriageGateConfig
from decision.triage_gate.stages.stage3_blast_radius import StrictBlastRadiusStage


def test_blast_radius_stage_evaluates_nominal_dimensions() -> None:
    """
    Control Invariant: Explicit calibrated blast radius dimensions in the raw payload
    are normalized to validated 5D BlastRadiusScore structures.
    """
    stage = StrictBlastRadiusStage(DEFAULT_CONFIG)

    payload = {
        "blast_radius": {
            "reversibility": "LOW",
            "cost": "MEDIUM",
            "relationship_impact": "LOW",
            "commitment": "LOW",
            "external_visibility": "LOW",
        }
    }

    context = WorkingContext(
        source_event_ids=("evt-blast-01",),
        raw_payload=payload,
        commitment_level="LOW",
        unknowns=(),
        assumptions=(),
    )

    score = stage.execute(context, ActionType.QUERY_INFO)

    assert score.reversibility == "LOW"
    assert score.cost == "MEDIUM"
    assert score.relationship_impact == "LOW"
    assert score.commitment == "LOW"
    assert score.external_visibility == "LOW"


def test_blast_radius_stage_mandatory_escalation_overrides_to_critical() -> None:
    """
    Control Invariant: Proposed actions listed in mandatory_escalation_actions
    automatically force reversibility, cost, and commitment dimensions to CRITICAL.
    """
    stage = StrictBlastRadiusStage(DEFAULT_CONFIG)

    payload = {
        "blast_radius": {
            "reversibility": "LOW",
            "cost": "LOW",
            "relationship_impact": "LOW",
            "commitment": "LOW",
            "external_visibility": "LOW",
        }
    }

    context = WorkingContext(
        source_event_ids=("evt-blast-02",),
        raw_payload=payload,
        commitment_level="LOW",
        unknowns=(),
        assumptions=(),
    )

    score = stage.execute(context, ActionType.PURGE_RECORDS)

    assert score.reversibility == "CRITICAL"
    assert score.cost == "CRITICAL"
    assert score.commitment == "CRITICAL"
    assert score.relationship_impact == "LOW"
    assert score.external_visibility == "LOW"


def test_blast_radius_ordinal_map_weights() -> None:
    """
    Control Invariant: Ordinal mapping reflects exact numeric weights:
    LOW=1, MEDIUM=2, HIGH=3, CRITICAL=4.
    """
    score = BlastRadiusScore(
        reversibility="LOW",
        cost="MEDIUM",
        relationship_impact="HIGH",
        commitment="CRITICAL",
        external_visibility="LOW",
    )

    ordinal_map = score.to_ordinal_map()

    assert ordinal_map == {
        "reversibility": 1,
        "cost": 2,
        "relationship_impact": 3,
        "commitment": 4,
        "external_visibility": 1,
    }
