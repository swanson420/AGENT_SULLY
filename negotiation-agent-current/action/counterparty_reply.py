"""Counterparty reply writer — persist only a scripted plant response.

The stored reply must match a fresh sandbox `respond()` on the same
inbound offer. ACCEPT echoes that offer. COUNTER equals the scripted
counter only. REJECT has no numbers. Anything else is unscripted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple

from action.settlement import AppendLedger
from adversarial.sandbox_vendor import VendorReply, respond

EVENT_TYPE = "counterparty_reply"

ALLOWED_DISPOSITIONS = frozenset({"ACCEPT", "COUNTER", "REJECT"})

REASON_UNVERIFIED_DISPOSITION = "UNVERIFIED_DISPOSITION"
REASON_UNSCRIPTED_CONCESSION = "UNSCRIPTED_CONCESSION"


class ReplyRefused(ValueError):
    """Unscripted or unverified plant reply — do not persist."""

    def __init__(self, reasons: Tuple[str, ...]) -> None:
        self.reasons = reasons
        super().__init__(
            "counterparty reply refused: " + ", ".join(reasons)
            if reasons
            else "counterparty reply refused"
        )


@dataclass(frozen=True)
class ReplyRecord:
    event_type: str
    disposition: str
    offer_usd: Optional[int]
    term_months: Optional[int]
    policy: str
    rationale: str
    evidence_event_ids: Tuple[str, ...]
    vendor_id: Optional[str]
    fixture: Optional[str]

    def to_payload(self) -> Mapping[str, Any]:
        return asdict(self)


def evaluate_reply(
    *,
    payload: Mapping[str, Any],
    inbound_offer_usd: int,
    inbound_term_months: int,
    reply: VendorReply,
    evidence_event_ids: Sequence[str] = (),
    vendor_id: Optional[str] = None,
    fixture: Optional[str] = None,
) -> ReplyRecord:
    if not isinstance(reply, VendorReply):
        raise ReplyRefused((REASON_UNVERIFIED_DISPOSITION,))
    if reply.disposition.name not in ALLOWED_DISPOSITIONS:
        raise ReplyRefused((REASON_UNVERIFIED_DISPOSITION,))

    expected = respond(payload, inbound_offer_usd, inbound_term_months)
    if reply != expected:
        raise ReplyRefused((REASON_UNSCRIPTED_CONCESSION,))

    return ReplyRecord(
        event_type=EVENT_TYPE,
        disposition=reply.disposition.name,
        offer_usd=reply.offer_usd,
        term_months=reply.term_months,
        policy=reply.policy,
        rationale=reply.rationale,
        evidence_event_ids=tuple(str(item) for item in evidence_event_ids),
        vendor_id=vendor_id,
        fixture=fixture,
    )


def write_reply(
    ledger: AppendLedger,
    event_id: str,
    **kwargs: Any,
) -> ReplyRecord:
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("event_id must be a non-empty string")
    record = evaluate_reply(**kwargs)
    ledger.append(event_id, record.to_payload())
    return record
