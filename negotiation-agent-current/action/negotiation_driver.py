"""Single-step negotiation driver.

Routes one outbound offer through the sandbox plant and, only if the
plant accepts terms the settlement writer will honor, writes a
settlement. Any constraint miss terminates the loop immediately. No
settlement event is emitted.

This module does not open a second bargaining round, invent an accept
of a counter, or call triage.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Mapping, Optional, Sequence, Tuple

from action.counterparty_reply import write_reply
from action.halt import (
    HaltRecord,
    REASON_CONSTRAINT,
    REASON_VENDOR_COUNTER,
    REASON_VENDOR_REJECT,
    write_halt,
)
from action.settlement import (
    AppendLedger,
    SettlementRecord,
    SettlementRefused,
    evaluate_settlement,
    write_settlement,
)
from adversarial.sandbox_vendor import VendorDisposition, VendorReply, respond


class DriverDisposition(Enum):
    SETTLED = auto()
    HALTED_REJECT = auto()
    HALTED_COUNTER = auto()
    HALTED_CONSTRAINT = auto()


@dataclass(frozen=True)
class DriverResult:
    disposition: DriverDisposition
    vendor_reply: Optional[VendorReply]
    settlement: Optional[SettlementRecord]
    halt: Optional[HaltRecord]
    refusal_reasons: Tuple[str, ...]


def _settlement_kwargs(
    payload: Mapping[str, Any],
    closed_usd: Any,
    term_months: Any,
    evidence_event_ids: Sequence[str],
) -> Mapping[str, Any]:
    return {
        "baseline_usd": payload.get("baseline_usd"),
        "closed_usd": closed_usd,
        "max_term_months": payload.get("max_term_months"),
        "term_months": term_months,
        "target_ceiling_usd": payload.get("target_ceiling_usd"),
        "forbidden_terms": payload.get("forbidden_terms") or (),
        "accepted_terms": (),
        "evidence_event_ids": evidence_event_ids,
        "vendor_id": payload.get("vendor_id"),
        "sku": payload.get("sku"),
        "currency": payload.get("currency") or "USD",
        "fixture": payload.get("fixture"),
    }


def _maybe_write_halt(
    ledger: Optional[AppendLedger],
    event_id: str,
    *,
    reason: str,
    detail_codes: Sequence[str] = (),
    evidence_event_ids: Sequence[str] = (),
    payload: Mapping[str, Any],
) -> Optional[HaltRecord]:
    if ledger is None:
        return None
    return write_halt(
        ledger,
        event_id,
        reason=reason,
        detail_codes=detail_codes,
        human_required=True,
        evidence_event_ids=evidence_event_ids,
        vendor_id=payload.get("vendor_id"),
        fixture=payload.get("fixture"),
    )


def drive(
    payload: Mapping[str, Any],
    offer_usd: Any,
    term_months: Any,
    *,
    ledger: Optional[AppendLedger] = None,
    settlement_event_id: str = "evt-settlement",
    halt_event_id: str = "evt-halt",
    reply_event_id: str = "evt-counterparty-reply",
    evidence_event_ids: Sequence[str] = (),
) -> DriverResult:
    """One offer → plant reply → settle or halt.

    Settlement is written only on plant ACCEPT whose terms pass
    evaluate_settlement. Any other terminal state appends a halt
    observation if a ledger is present. Prior entries are not edited.
    """
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")

    reply = respond(payload, offer_usd, term_months)
    if ledger is not None:
        write_reply(
            ledger,
            reply_event_id,
            payload=payload,
            inbound_offer_usd=offer_usd,
            inbound_term_months=term_months,
            reply=reply,
            evidence_event_ids=evidence_event_ids,
            vendor_id=payload.get("vendor_id"),
            fixture=payload.get("fixture"),
        )
        evidence_event_ids = tuple(evidence_event_ids) + (reply_event_id,)

    if reply.disposition is VendorDisposition.REJECT:
        halt = _maybe_write_halt(
            ledger,
            halt_event_id,
            reason=REASON_VENDOR_REJECT,
            evidence_event_ids=evidence_event_ids,
            payload=payload,
        )
        return DriverResult(
            disposition=DriverDisposition.HALTED_REJECT,
            vendor_reply=reply,
            settlement=None,
            halt=halt,
            refusal_reasons=(),
        )

    try:
        record = evaluate_settlement(
            **_settlement_kwargs(
                payload,
                reply.offer_usd,
                reply.term_months,
                evidence_event_ids,
            )
        )
    except SettlementRefused as refused:
        halt = _maybe_write_halt(
            ledger,
            halt_event_id,
            reason=REASON_CONSTRAINT,
            detail_codes=refused.reasons,
            evidence_event_ids=evidence_event_ids,
            payload=payload,
        )
        return DriverResult(
            disposition=DriverDisposition.HALTED_CONSTRAINT,
            vendor_reply=reply,
            settlement=None,
            halt=halt,
            refusal_reasons=refused.reasons,
        )

    if reply.disposition is VendorDisposition.COUNTER:
        halt = _maybe_write_halt(
            ledger,
            halt_event_id,
            reason=REASON_VENDOR_COUNTER,
            evidence_event_ids=evidence_event_ids,
            payload=payload,
        )
        return DriverResult(
            disposition=DriverDisposition.HALTED_COUNTER,
            vendor_reply=reply,
            settlement=None,
            halt=halt,
            refusal_reasons=(),
        )

    if ledger is not None:
        written = write_settlement(
            ledger,
            settlement_event_id,
            **_settlement_kwargs(
                payload,
                reply.offer_usd,
                reply.term_months,
                evidence_event_ids,
            ),
        )
        return DriverResult(
            disposition=DriverDisposition.SETTLED,
            vendor_reply=reply,
            settlement=written,
            halt=None,
            refusal_reasons=(),
        )

    return DriverResult(
        disposition=DriverDisposition.SETTLED,
        vendor_reply=reply,
        settlement=record,
        halt=None,
        refusal_reasons=(),
    )
