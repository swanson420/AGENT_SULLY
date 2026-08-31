import pytest

from decision.contracts.decision_package import (
    WorkingContext,
    ActionType,
)
from decision.contracts.blast_radius import BlastRadiusScore
from decision.triage_gate.config import DEFAULT_CONFIG
from decision.triage_gate.stages.stage3_blast_radius import StrictBlastRadiusStage


def test_blast_radius_uncalibrated_commitment_fails_closed_to_critical() -> None:
    """
    Control Invariant: An unrecognized or uncalibrated commitment string
    must fail closed to CRITICAL (4), preventing silent bypass under ambiguous inputs.
    """
    stage = StrictBlastRadiusStage(DEFAULT_CONFIG)

    payload = {
        "blast_radius": {
            "reversibility": "LOW",
            "cost": "LOW",
            "relationship_impact": "LOW",
            "commitment": "INDETERMINATE_ARBITRARY_VALUE",
            "external_visibility": "LOW",
        }
    }

    context = WorkingContext(
        source_event_ids=("evt-failclose-01",),
        raw_payload=payload,
        commitment_level="INDETERMINATE_ARBITRARY_VALUE",
        unknowns=(),
        assumptions=(),
    )

    score = stage.execute(context, ActionType.QUERY_INFO)

    assert score.commitment == "CRITICAL"
    assert score.reversibility == "LOW"
    assert score.cost == "LOW"


def test_blast_radius_missing_commitment_fails_closed_to_critical() -> None:
    """
    Control Invariant: When commitment is omitted or None across both context
    and payload, Stage 3 enforces a fail-closed default of CRITICAL.
    """
    stage = StrictBlastRadiusStage(DEFAULT_CONFIG)

    payload = {
        "blast_radius": {
            "reversibility": "LOW",
            "cost": "LOW",
            "relationship_impact": "LOW",
            "external_visibility": "LOW",
        }
    }

    context = WorkingContext(
        source_event_ids=("evt-failclose-02",),
        raw_payload=payload,
        commitment_level=None,
        unknowns=(),
        assumptions=(),
    )

    score = stage.execute(context, ActionType.QUERY_INFO)

    assert score.commitment == "CRITICAL"
