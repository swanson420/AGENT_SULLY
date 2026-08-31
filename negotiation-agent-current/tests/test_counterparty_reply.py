"""Reply writer: scripted plant only. Forged concessions do not persist."""

from __future__ import annotations

import pytest

from action.counterparty_reply import (
    REASON_UNSCRIPTED_CONCESSION,
    REASON_UNVERIFIED_DISPOSITION,
    ReplyRefused,
    evaluate_reply,
    write_reply,
)
from adversarial.sandbox_vendor import VendorDisposition, VendorReply, respond
from ledger.ledger import Ledger
from scenarios.vendor_renewal.scenario import (
    MAX_TERM_MONTHS,
    TARGET_CEILING_USD,
    build_raw_event_payload,
)


def _unused_aggregator(event_ids, lookup):
    return {}, ""


def test_accept_reply_matches_fresh_plant_and_chains():
    payload = build_raw_event_payload("easy_save")
    reply = respond(payload, TARGET_CEILING_USD, MAX_TERM_MONTHS)
    ledger = Ledger(aggregator=_unused_aggregator)
    ledger.append("evt-baseline-1", {"event_type": "baseline"})
    record = write_reply(
        ledger,
        "evt-reply-1",
        payload=payload,
        inbound_offer_usd=TARGET_CEILING_USD,
        inbound_term_months=MAX_TERM_MONTHS,
        reply=reply,
        evidence_event_ids=("evt-baseline-1",),
    )
    assert record.disposition == "ACCEPT"
    assert record.offer_usd == TARGET_CEILING_USD
    assert ledger.entries[1]["payload"]["event_type"] == "counterparty_reply"
    assert ledger.entries[1]["prev_hash"] == ledger.entries[0]["hash"]


def test_forged_cheaper_accept_is_unscripted():
    payload = build_raw_event_payload("easy_save")
    forged = VendorReply(
        disposition=VendorDisposition.ACCEPT,
        offer_usd=30000,
        term_months=MAX_TERM_MONTHS,
        policy="accept_if_price_at_or_above_floor_and_term_at_or_below_required",
        rationale="friendly discount",
    )
    with pytest.raises(ReplyRefused) as refused:
        evaluate_reply(
            payload=payload,
            inbound_offer_usd=TARGET_CEILING_USD,
            inbound_term_months=MAX_TERM_MONTHS,
            reply=forged,
        )
    assert REASON_UNSCRIPTED_CONCESSION in refused.value.reasons


def test_unknown_disposition_is_refused():
    payload = build_raw_event_payload("easy_save")
    with pytest.raises(ReplyRefused) as refused:
        evaluate_reply(
            payload=payload,
            inbound_offer_usd=TARGET_CEILING_USD,
            inbound_term_months=MAX_TERM_MONTHS,
            reply="ACCEPT",
        )
    assert REASON_UNVERIFIED_DISPOSITION in refused.value.reasons


def test_refusal_writes_nothing():
    payload = build_raw_event_payload("no_give")
    forged = VendorReply(
        disposition=VendorDisposition.COUNTER,
        offer_usd=38000,
        term_months=24,
        policy="reject_below_floor_no_concession",
        rationale="invented counter",
    )
    ledger = Ledger(aggregator=_unused_aggregator)
    with pytest.raises(ReplyRefused):
        write_reply(
            ledger,
            "evt-reply-1",
            payload=payload,
            inbound_offer_usd=TARGET_CEILING_USD,
            inbound_term_months=MAX_TERM_MONTHS,
            reply=forged,
        )
    assert ledger.entries == ()
