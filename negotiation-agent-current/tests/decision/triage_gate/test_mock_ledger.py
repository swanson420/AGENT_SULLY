# tests/decision/triage_gate/test_mock_ledger.py
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence
import pytest

from decision.contracts.decision_package import (
    WorkingContext,
    DecisionRecord,
    RouteType,
    ActionType,
)
from decision.contracts.blast_radius import BlastRadiusScore
from decision.triage_gate.base import LedgerProtocol
from decision.triage_gate.provenance import ProvenanceEngine


class MockLedger:
    """Hermetic, non-hash-chained ledger double implementing LedgerProtocol.

    This existed as an import-only scaffold before this fix -- imports
    with no class, no test functions. Its one real consumer,
    test_fixture_isolation_coexistence.py, was already written against a
    specific expected shape: MockLedger(), .record_event(event_id, payload),
    a ._events mapping keyed by event_id, and .get_event(event_id)
    returning a mapping containing "payload". Built to match that
    consumer exactly, not guessed independently of it.

    Unlike ledger.ledger.Ledger, this does not hash-chain entries -- it
    exists for tests that need an isolated, disposable ledger double
    without caring about chain-integrity behavior (that's what
    ledger.ledger.Ledger and tests/test_ledger.py are for).
    """

    def __init__(self) -> None:
        self._events: Dict[str, Dict[str, Any]] = {}

    def record_event(self, event_id: str, payload: Mapping[str, Any]) -> None:
        """Store an event under event_id. Last write wins -- no
        duplicate-ID rejection here, unlike the real Ledger; this is a
        disposable test double, not an audit-integrity guarantee."""
        self._events[event_id] = {
            "event_id": event_id,
            "payload": dict(payload),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_event(self, event_id: str) -> Optional[Mapping[str, Any]]:
        """LedgerProtocol method."""
        return self._events.get(event_id)

    def verify_provenance(self, event_ids: Sequence[str], expected_hash: str) -> bool:
        """LedgerProtocol method. Same canonical aggregation the real
        Ledger uses, so a test can swap MockLedger in for Ledger without
        the provenance-checking gate behaving differently."""
        if not event_ids or not expected_hash:
            return False
        lookup: Dict[str, Mapping[str, Any]] = {}
        for event_id in event_ids:
            event = self.get_event(event_id)
            if event is None:
                return False
            lookup[event_id] = event
        _, computed = ProvenanceEngine.aggregate_event_payloads(event_ids, lookup)
        return computed == expected_hash

    def record_decision_view(self, record: DecisionRecord) -> bool:
        """LedgerProtocol method. No hash-chain to validate against, so
        this is simpler than Ledger's version -- just validate and store,
        idempotent on a repeated identical audit_hash the same way
        ledger.ledger.Ledger is."""
        try:
            record.validate()
        except (TypeError, ValueError):
            return False
        event_id = f"decision:{record.audit_hash}"
        existing = self._events.get(event_id)
        payload = {"route": record.route.name, "action": record.action.name}
        if existing is not None:
            return existing["payload"] == payload
        self.record_event(event_id, payload)
        return True

