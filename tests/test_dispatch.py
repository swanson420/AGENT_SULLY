from datetime import datetime, timezone

import pytest

from action.dispatch import dispatch
from decision.contracts.blast_radius import BlastRadiusScore
from decision.contracts.decision_package import (
    ActionType,
    DecisionRecord,
    RouteType,
    WorkingContext,
)


class FakeLedger:
    def __init__(self, accepted=True):
        self.accepted = accepted
        self.calls = []

    def record_decision_view(self, record):
        self.calls.append(record)
        return self.accepted


def record(route=RouteType.ACT_SILENTLY):
    context = WorkingContext(
        source_event_ids=("real-event-1",),
        raw_payload={"scenario": "internet-bill"},
    )
    return DecisionRecord(
        route=route,
        action=ActionType.QUERY_INFO,
        context=context,
        blast_radius=BlastRadiusScore(
            reversibility="LOW", cost="LOW", relationship_impact="LOW",
            commitment="LOW", external_visibility="LOW",
        ),
        gate_results={"policy": True},
        audit_hash="a" * 64,
        timestamp=datetime.now(timezone.utc),
        rationale="query information conservatively",
    )


def test_audit_commit_precedes_target_delivery():
    ledger = FakeLedger()
    order = []

    def audited(record):
        order.append("audit")
        return True

    ledger.record_decision_view = audited

    def target(record):
        order.append("target")
        return "delivered"

    assert dispatch(record(), ledger, target) == "delivered"
    assert order == ["audit", "target"]


def test_failed_audit_blocks_target():
    ledger = FakeLedger(accepted=False)
    delivered = []

    with pytest.raises(RuntimeError, match="audit commitment failed"):
        dispatch(record(), ledger, lambda value: delivered.append(value))

    assert delivered == []
    assert len(ledger.calls) == 1


def test_non_silent_route_blocks_before_audit_or_target():
    ledger = FakeLedger()
    delivered = []

    with pytest.raises(ValueError, match="ACT_SILENTLY"):
        dispatch(record(RouteType.BOUNCE_DOMAIN), ledger, lambda value: delivered.append(value))

    assert ledger.calls == []
    assert delivered == []


def test_default_slice0_delivery_requires_audit():
    ledger = FakeLedger()
    assert dispatch(record(), ledger) == "success"
    assert len(ledger.calls) == 1
