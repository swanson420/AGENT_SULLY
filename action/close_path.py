"""Visible close path: baseline → offer → settle-or-halt → export.

One run of the vendor-renewal loop against a concrete ledger. The export
is rebuilt from ledger entries plus a fresh metrics scan. No second
store. No triage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping, Optional, Sequence, Tuple

from action.commitment_gradient import classify_commitment_level
from action.dispatch_gate import assert_dispatch_allowed
from action.human_ack import write_human_ack
from action.mailbox import send_offer
from decision.triage_gate.config import DEFAULT_CONFIG
from action.negotiation_driver import DriverDisposition, DriverResult, drive
from action.offer import SCOPE_SYNTHETIC_OFFER_TEXT, OfferRecord
from action.offer_bind import bind_and_write_offer
from adversarial.counterparty_model import CounterpartyModel
from decision.contracts.blast_radius import BlastRadiusScore
from decision.contracts.decision_package import (
    ActionType,
    DecisionRecord,
    RouteType,
    WorkingContext,
)
from feedback.metrics import MetricsSnapshot, collect
from ledger.ledger import Ledger
from scenarios.vendor_renewal.scenario import (
    EASY_SAVE_TERM_MONTHS,
    EASY_SAVE_USD,
    VALID_FIXTURES,
    build_raw_event_payload,
)

BASELINE_EVENT_ID = "evt-baseline-1"
OFFER_EVENT_ID = "evt-offer-1"
HUMAN_ACK_EVENT_ID = "evt-human-ack-1"
SETTLEMENT_EVENT_ID = "evt-settlement-1"
HALT_EVENT_ID = "evt-halt-1"
MAILBOX_EVENT_ID = "evt-offer-sent-1"
REPLY_EVENT_ID = "evt-counterparty-reply-1"

TRIGGER_NONE = "none"
TRIGGER_MANDATORY_ESCALATION = "mandatory_escalation"
TRIGGER_BLAST_ORDINAL = "blast_ordinal"

OFFER_ACTION = ActionType.EXECUTE_QUERY


def _unused_aggregator(event_ids, lookup):
    return {}, ""


def _snapshot_to_dict(snap: MetricsSnapshot) -> Mapping[str, Any]:
    return {
        "baseline_count": snap.baseline_count,
        "settlement_count": snap.settlement_count,
        "invalid_settlement_count": snap.invalid_settlement_count,
        "halt_count": snap.halt_count,
        "invalid_halt_count": snap.invalid_halt_count,
        "halt_by_reason": dict(snap.halt_by_reason),
        "constraint_by_detail": dict(snap.constraint_by_detail),
        "total_savings_usd": snap.total_savings_usd,
    }


def _event_view(entry: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = entry.get("payload") or {}
    return {
        "event_id": entry.get("event_id"),
        "event_type": payload.get("event_type"),
        "prev_hash": entry.get("prev_hash"),
        "hash": entry.get("hash"),
        "payload": payload,
    }


@dataclass(frozen=True)
class ClosePathResult:
    fixture: str
    offer_usd: int
    term_months: int
    disposition: DriverDisposition
    offer: OfferRecord
    driver: DriverResult
    metrics: MetricsSnapshot
    export: Mapping[str, Any]


def _blast_from_payload(payload: Mapping[str, Any]) -> BlastRadiusScore:
    raw = payload.get("blast_radius") or {}
    return BlastRadiusScore(
        reversibility=raw.get("reversibility", "MEDIUM"),
        cost=raw.get("cost", "MEDIUM"),
        relationship_impact=raw.get("relationship_impact", "MEDIUM"),
        commitment=raw.get("commitment", "MEDIUM"),
        external_visibility=raw.get("external_visibility", "MEDIUM"),
    )


def _offer_record(
    payload: Mapping[str, Any],
    offer_usd: int,
    term_months: int,
    blast: BlastRadiusScore,
) -> DecisionRecord:
    text = f"Offer {offer_usd} USD for {term_months} months."
    material = json.dumps(
        {"offer_usd": offer_usd, "term_months": term_months},
        sort_keys=True,
        separators=(",", ":"),
    )
    return DecisionRecord(
        route=RouteType.ACT_SILENTLY,
        action=OFFER_ACTION,
        context=WorkingContext(
            source_event_ids=(BASELINE_EVENT_ID,),
            raw_payload={"message": text},
            commitment_level="MEDIUM",
        ),
        blast_radius=blast,
        gate_results={"interpretation_stable": True},
        audit_hash=sha256(material.encode("utf-8")).hexdigest(),
        timestamp=datetime.now(timezone.utc),
        rationale="Outbound vendor-renewal offer.",
    )


def _real_classify(action: ActionType, blast: BlastRadiusScore) -> int:
    return classify_commitment_level(action, blast)


def _real_assess(record: DecisionRecord):
    return CounterpartyModel().assess(record)


def _commitment_trigger(action: ActionType, level: int) -> str:
    if action in DEFAULT_CONFIG.mandatory_escalation_actions:
        return TRIGGER_MANDATORY_ESCALATION
    if level >= 3:
        return TRIGGER_BLAST_ORDINAL
    return TRIGGER_NONE


def close_path(
    fixture: str,
    *,
    offer_usd: Optional[int] = None,
    term_months: Optional[int] = None,
    ledger: Optional[Ledger] = None,
    classify_fn=None,
    assess_fn=None,
    grant_human_ack: bool = False,
    offer_action: Optional[ActionType] = None,
) -> ClosePathResult:
    """Append baseline, gate the offer, persist offer, then settle or halt."""
    if fixture not in VALID_FIXTURES:
        raise ValueError(f"unknown fixture: {fixture!r}")

    payload = dict(build_raw_event_payload(fixture))
    payload["event_type"] = "baseline"
    dollars = EASY_SAVE_USD if offer_usd is None else offer_usd
    term = EASY_SAVE_TERM_MONTHS if term_months is None else term_months

    book = ledger if ledger is not None else Ledger(aggregator=_unused_aggregator)
    book.append(BASELINE_EVENT_ID, payload)

    blast = _blast_from_payload(payload)
    action = offer_action if offer_action is not None else OFFER_ACTION
    decision = _offer_record(payload, dollars, term, blast)
    # DecisionRecord.action stays EXECUTE_QUERY in the assess package;
    # classify uses `action` so MUTATE_STATE can fire the real ≥3 path.
    resolved_classify = classify_fn or (lambda: _real_classify(action, blast))
    level = resolved_classify()
    if grant_human_ack:
        write_human_ack(
            book,
            HUMAN_ACK_EVENT_ID,
            granted=True,
            evidence_event_ids=(BASELINE_EVENT_ID,),
            fixture=fixture,
        )
    assert_dispatch_allowed(level, book, BASELINE_EVENT_ID)
    offer = bind_and_write_offer(
        book,
        OFFER_EVENT_ID,
        offer_usd=dollars,
        term_months=term,
        classify_fn=lambda: level,
        assess_fn=assess_fn or (lambda: _real_assess(decision)),
        evidence_event_ids=(BASELINE_EVENT_ID,),
        vendor_id=payload.get("vendor_id"),
        sku=payload.get("sku"),
        currency=payload.get("currency") or "USD",
        fixture=fixture,
        adversarial_check_scope=SCOPE_SYNTHETIC_OFFER_TEXT,
    )
    send_offer(
        book,
        MAILBOX_EVENT_ID,
        evidence_event_ids=(BASELINE_EVENT_ID, OFFER_EVENT_ID),
        fixture=fixture,
    )

    driver = drive(
        payload,
        dollars,
        term,
        ledger=book,
        settlement_event_id=SETTLEMENT_EVENT_ID,
        halt_event_id=HALT_EVENT_ID,
        reply_event_id=REPLY_EVENT_ID,
        evidence_event_ids=(BASELINE_EVENT_ID, OFFER_EVENT_ID, MAILBOX_EVENT_ID),
    )
    metrics = collect(book)
    export = {
        "fixture": fixture,
        "offer_usd": dollars,
        "term_months": term,
        "disposition": driver.disposition.name,
        "adversarial_check_scope": offer.adversarial_check_scope,
        "commitment_trigger": _commitment_trigger(action, level),
        "commitment_level": level,
        "events": [_event_view(entry) for entry in book.entries],
        "metrics": _snapshot_to_dict(metrics),
    }
    return ClosePathResult(
        fixture=fixture,
        offer_usd=dollars,
        term_months=term,
        disposition=driver.disposition,
        offer=offer,
        driver=driver,
        metrics=metrics,
        export=export,
    )


def export_json(result: ClosePathResult) -> str:
    return json.dumps(result.export, sort_keys=True, indent=2, default=str)


def run_all(fixtures: Sequence[str] = VALID_FIXTURES) -> Tuple[ClosePathResult, ...]:
    return tuple(close_path(fixture) for fixture in fixtures)


def witnessed_close_path(
    fixture: str = "easy_save",
    **kwargs: Any,
) -> ClosePathResult:
    """Real classifier fire: MUTATE_STATE → level 5 → requires human_ack."""
    kwargs.setdefault("offer_action", ActionType.MUTATE_STATE)
    kwargs.setdefault("grant_human_ack", True)
    return close_path(fixture, **kwargs)


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    witnessed = "--witnessed" in args
    args = [item for item in args if item != "--witnessed"]
    name = args[0] if args else "easy_save"
    result = witnessed_close_path(name) if witnessed else close_path(name)
    print(export_json(result))
