from datetime import datetime, timezone

import pytest

from adversarial.counterparty_model import AdversarialDisposition, CounterpartyModel
from decision.contracts.decision_package import (
    ActionType,
    DecisionRecord,
    RouteType,
    WorkingContext,
)
from decision.contracts.blast_radius import BlastRadiusScore


def make_record(text: str) -> DecisionRecord:
    return DecisionRecord(
        route=RouteType.ACT_SILENTLY,
        action=ActionType.QUERY_INFO,
        context=WorkingContext(
            source_event_ids=("evt-1",),
            raw_payload={"message": text},
            commitment_level="LOW",
        ),
        blast_radius=BlastRadiusScore(
            reversibility="LOW", cost="LOW", relationship_impact="LOW",
            commitment="LOW", external_visibility="LOW",
        ),
        gate_results={"interpretation_stable": True},
        audit_hash="0" * 64,
        timestamp=datetime.now(timezone.utc),
        rationale="ordinary action",
    )


def test_nominal_counterparty_passes() -> None:
    result = CounterpartyModel().assess(make_record("Please review the current invoice."))
    assert result.disposition is AdversarialDisposition.PASS
    assert result.route is RouteType.ACT_SILENTLY
    assert result.next_recursion_depth == 0


def test_first_objection_allows_exactly_one_loop_back() -> None:
    result = CounterpartyModel().assess(make_record("This is your final offer; decide now."))
    assert result.disposition is AdversarialDisposition.LOOP_BACK
    assert result.next_recursion_depth == 1
    assert result.objections


def test_second_objection_bounces_instead_of_looping_again() -> None:
    result = CounterpartyModel().assess(
        make_record("This is your final offer; decide now."),
        recursion_depth=1,
    )
    assert result.disposition is AdversarialDisposition.BOUNCE_DOMAIN
    assert result.route is RouteType.BOUNCE_DOMAIN
    assert result.next_recursion_depth == 1


def test_depth_never_exceeds_configured_cap() -> None:
    model = CounterpartyModel()
    result = model.assess(make_record("deadline today"), recursion_depth=2)
    assert result.disposition is AdversarialDisposition.BOUNCE_DOMAIN
    assert result.next_recursion_depth == 2


def test_negative_depth_rejected() -> None:
    with pytest.raises(ValueError):
        CounterpartyModel().assess(make_record("normal"), recursion_depth=-1)
