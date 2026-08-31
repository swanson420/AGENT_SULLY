"""Human acknowledgement — the only event that opens a ≥3 dispatch."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple

from action.settlement import AppendLedger

EVENT_TYPE = "human_ack"


class HumanAckRefused(ValueError):
    """Unverified ack — do not persist."""


@dataclass(frozen=True)
class HumanAckRecord:
    event_type: str
    granted: bool
    evidence_event_ids: Tuple[str, ...]
    actor: str
    fixture: Optional[str]

    def to_payload(self) -> Mapping[str, Any]:
        return asdict(self)


def evaluate_human_ack(
    *,
    granted: Any = True,
    evidence_event_ids: Sequence[str] = (),
    actor: str = "human",
    fixture: Optional[str] = None,
) -> HumanAckRecord:
    if granted is not True:
        raise HumanAckRefused("human_ack requires granted=True")
    if not isinstance(actor, str) or not actor:
        raise HumanAckRefused("actor must be a non-empty string")
    return HumanAckRecord(
        event_type=EVENT_TYPE,
        granted=True,
        evidence_event_ids=tuple(str(item) for item in evidence_event_ids),
        actor=actor,
        fixture=fixture,
    )


def write_human_ack(
    ledger: AppendLedger,
    event_id: str,
    **kwargs: Any,
) -> HumanAckRecord:
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("event_id must be a non-empty string")
    record = evaluate_human_ack(**kwargs)
    ledger.append(event_id, record.to_payload())
    return record


def ledger_has_granted_ack(ledger: Any, required_evidence_event_id: Optional[str] = None) -> bool:
    """True if a granted human_ack exists. If required_evidence_event_id is
    given, the ack must actually reference that event — not just be some
    granted ack anywhere on the ledger. Without this, an ack granted for
    one negotiation would silently authorize a different, later
    negotiation sharing the same ledger. required_evidence_event_id is
    optional (defaults to the old any-ack behavior) only for backward
    compatibility with direct callers; assert_dispatch_allowed always
    passes it."""
    entries = getattr(ledger, "entries", ())
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        payload = entry.get("payload") or {}
        if payload.get("event_type") != EVENT_TYPE or payload.get("granted") is not True:
            continue
        if required_evidence_event_id is None:
            return True
        if required_evidence_event_id in (payload.get("evidence_event_ids") or ()):
            return True
    return False
