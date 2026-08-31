"""Minimal in-memory append-only, hash-chained ledger."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from copy import deepcopy

from decision.contracts.decision_package import DecisionRecord

from .hash_chain import chain_hash

# Signature the ledger requires from any provenance aggregator: given event
# IDs and an event lookup, return (collated_payloads, canonical_digest).
ProvenanceAggregator = Callable[
    [Sequence[str], Mapping[str, Mapping[str, Any]]], Tuple[Dict[str, Any], str]
]


def _default_aggregator() -> ProvenanceAggregator:
    """Resolve the decision layer's canonical aggregator lazily.

    Deliberately not a module-level import: ledger/ must stay a leaf at
    parse time. The decision layer is only touched at construction time,
    by whichever caller wires the two together, and only if no aggregator
    was explicitly injected.
    """
    from decision.triage_gate.provenance import ProvenanceEngine

    return ProvenanceEngine.aggregate_event_payloads


class Ledger:
    """In-memory ledger implementing the decision layer's ``LedgerProtocol``.

    The ledger has one write operation: :meth:`append`. Before every append,
    the existing chain is re-verified. If any stored entry has been altered,
    the incoming record is rejected and nothing is persisted.

    Provenance verification is delegated to an injected aggregator callable
    rather than a hard import, so this module has no static (parse-time)
    dependency on the decision layer. Callers that don't care can ignore
    ``aggregator`` entirely and get the canonical decision-layer behavior
    by default.
    """

    def __init__(self, aggregator: Optional[ProvenanceAggregator] = None) -> None:
        self._entries: List[Dict[str, Any]] = []
        self._events: Dict[str, Dict[str, Any]] = {}
        self._aggregator = aggregator or _default_aggregator()

    @property
    def entries(self) -> Sequence[Mapping[str, Any]]:
        """Return an immutable snapshot of ledger entries."""
        return tuple(deepcopy(entry) for entry in self._entries)

    def _chain_is_valid(self) -> bool:
        """Validate every stored entry's predecessor and content hash."""
        previous_hash = ""
        for entry in self._entries:
            if entry.get("prev_hash") != previous_hash:
                return False
            payload = entry.get("payload")
            if not isinstance(payload, Mapping):
                return False
            expected_hash = chain_hash(previous_hash, payload)
            if entry.get("hash") != expected_hash:
                return False
            previous_hash = expected_hash
        return True

    def append(self, event_id: str, payload: Mapping[str, Any]) -> str:
        """Append one event, rejecting duplicate IDs or broken chain state."""
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("event_id must be a non-empty string")
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
        if event_id in self._events:
            raise ValueError(f"event_id already exists: {event_id}")

        # Critical control point: validate continuity BEFORE creating the new
        # entry, so a corrupted chain can never be extended silently.
        if not self._chain_is_valid():
            raise ValueError("ledger hash continuity validation failed")

        prev_hash = self._entries[-1]["hash"] if self._entries else ""
        payload_snapshot = deepcopy(dict(payload))
        entry_hash = chain_hash(prev_hash, payload_snapshot)
        entry = {
            "event_id": event_id,
            "payload": payload_snapshot,
            "prev_hash": prev_hash,
            "hash": entry_hash,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self._entries.append(entry)
        self._events[event_id] = entry
        return entry_hash

    def get_event(self, event_id: str) -> Optional[Mapping[str, Any]]:
        """Fetch an event by ID without exposing mutable ledger state."""
        entry = self._events.get(event_id)
        return deepcopy(entry) if entry is not None else None

    @staticmethod
    def _canonicalize(value: Any) -> Any:
        """Normalize common Python values to deterministic JSON-compatible data."""
        if isinstance(value, Mapping):
            return {str(key): Ledger._canonicalize(value[key]) for key in sorted(value, key=str)}
        if isinstance(value, (list, tuple)):
            return [Ledger._canonicalize(item) for item in value]
        if isinstance(value, (set, frozenset)):
            normalized = [Ledger._canonicalize(item) for item in value]
            return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Enum):
            # Found while fixing the same class of bug in
            # decision/triage_gate/provenance.py's _normalize_structure:
            # the two canonicalizers previously disagreed on the same
            # RouteType value -- this one returned .value (a bare
            # meaningless int from auto(), e.g. 1), the other returned
            # .name ("ACT_SILENTLY") once fixed. Aligned here to .name
            # for the same reason: this codebase's enums use auto() for
            # values, so .value carries no information a reader could
            # use, while .name is the stable, human-readable identifier.
            # No existing test in tests/test_ledger.py asserts a specific
            # route/action serialization, so this was silently
            # inconsistent rather than actively broken -- confirmed via
            # grep before making this change.
            return value.name
        if is_dataclass(value):
            return Ledger._canonicalize(asdict(value))
        if isinstance(value, (bytes, bytearray)):
            return value.hex()
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    def verify_provenance(self, event_ids: Sequence[str], expected_hash: str) -> bool:
        """Verify the deterministic aggregate payload hash for the given events."""
        if not event_ids or not expected_hash:
            return False

        lookup: Dict[str, Mapping[str, Any]] = {}
        for event_id in event_ids:
            event = self.get_event(event_id)
            if event is None:
                return False
            lookup[event_id] = event

        # Delegate to the injected aggregator (decision-layer canonical
        # implementation by default) rather than a second hashing convention
        # defined here.
        _, computed = self._aggregator(event_ids, lookup)
        return computed == expected_hash

    def record_decision_view(self, record: DecisionRecord) -> bool:
        """Validate and append a decision record as an immutable ledger event.

        Idempotent by audit_hash: the same DecisionRecord may legitimately
        be audited more than once by different callers in one pipeline pass
        (e.g. the triage pipeline's own audit stage, which always runs
        regardless of route, and dispatch's separate pre-delivery audit
        gate, which exists so delivery can never happen without an audit
        commit even if something calls dispatch directly). A second commit
        of an *identical* payload under the same event_id is a confirmation,
        not a corruption, and must not be rejected the same way a genuinely
        conflicting write is. Discovered by running the real, unmocked
        Ledger + triage + dispatch chain together, not anticipated in
        advance -- action/dispatch.py and decision/triage_gate/stages/
        stage5_audit.py were each built as though they were the only writer
        of a given decision's audit trail.
        """
        try:
            record.validate()
            payload = self._canonicalize(record)
            event_id = f"decision:{record.audit_hash}"

            existing = self._events.get(event_id)
            if existing is not None:
                # Same ID reappearing with a different payload is a real
                # conflict (e.g. an audit_hash collision) and must still
                # fail closed. Same ID with the same payload is just this
                # decision being audited a second time.
                return existing["payload"] == payload

            self.append(event_id, payload)
            return True
        except (TypeError, ValueError, KeyError):
            return False
