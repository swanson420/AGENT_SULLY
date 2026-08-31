from datetime import datetime, timezone

import pytest

from action.action_gate import ActionGate, action_gate
from decision.contracts.decision_package import (
    ActionType,
    DecisionRecord,
    RouteType,
    WorkingContext,
)
from decision.contracts.blast_radius import BlastRadiusScore


def make_record(route=RouteType.ACT_SILENTLY):
    context = WorkingContext(
        source_event_ids=("event-1",),
        raw_payload={"scenario": "internet-bill"},
    )
    return DecisionRecord(
        route=route,
        action=ActionType.QUERY_INFO,
        context=context,
        blast_radius=BlastRadiusScore(
            reversibility="LOW",
            cost="LOW",
            relationship_impact="LOW",
            commitment="LOW",
            external_visibility="LOW",
        ),
        gate_results={
            "interpretation_stable": True,
            "context_anchored": True,
            "ledger_anchored": True,
            "blast_radius_calibrated": True,
            "assumptions_grounded": True,
        },
        audit_hash="a" * 64,
        timestamp=datetime.now(timezone.utc),
        rationale="All required gates passed.",
    )


def test_silent_route_calls_dispatch():
    calls = []
    record = make_record()

    result = action_gate(record, lambda r: calls.append(r) or "sent")

    assert result == "sent"
    assert calls == [record]


def test_non_silent_route_does_not_dispatch():
    calls = []
    record = make_record(RouteType.BOUNCE_DOMAIN)

    result = action_gate(record, lambda r: calls.append(r) or "sent")

    assert result is None
    assert calls == []


def test_invalid_record_is_rejected_before_dispatch():
    calls = []
    record = make_record()
    object.__setattr__(record, "audit_hash", "bad")

    with pytest.raises(ValueError):
        action_gate(record, lambda r: calls.append(r))

    assert calls == []


def test_object_wrapper_uses_same_gate():
    record = make_record()
    gate = ActionGate(lambda r: "ok")

    assert gate.execute(record) == "ok"
