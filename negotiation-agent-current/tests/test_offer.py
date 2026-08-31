"""Offer writer: valid terms + verified signals chain; malformed writes nothing."""

from __future__ import annotations

import pytest

from action.offer import (
    DISPOSITION_PASS,
    SCOPE_SYNTHETIC_OFFER_TEXT,
    OfferRefused,
    REASON_INVALID_ADVERSARIAL_DISPOSITION,
    REASON_INVALID_COMMITMENT_LEVEL,
    REASON_INVALID_OFFER_USD,
    REASON_INVALID_TERM,
    adversarial_digest,
    evaluate_offer,
    write_offer,
)
from ledger.hash_chain import chain_hash
from ledger.ledger import Ledger
from scenarios.vendor_renewal.scenario import (
    MAX_TERM_MONTHS,
    TARGET_CEILING_USD,
    build_raw_event_payload,
)


def _unused_aggregator(event_ids, lookup):
    return {}, ""


def _valid_kwargs(**overrides):
    values = {
        "offer_usd": TARGET_CEILING_USD,
        "term_months": MAX_TERM_MONTHS,
        "commitment_level": 2,
        "adversarial_disposition": DISPOSITION_PASS,
        "adversarial_objections": (),
        "adversarial_rationale": "No material counterparty objection detected.",
        "evidence_event_ids": ("evt-baseline-1",),
        "vendor_id": "acme-analytics",
        "sku": "analytics-platform-50",
        "currency": "USD",
        "fixture": "easy_save",
    }
    values.update(overrides)
    return values


def test_evaluate_records_commitment_and_digest():
    record = evaluate_offer(**_valid_kwargs())
    assert record.event_type == "offer"
    assert record.offer_usd == TARGET_CEILING_USD
    assert record.term_months == MAX_TERM_MONTHS
    assert record.commitment_level == 2
    assert record.adversarial_disposition == DISPOSITION_PASS
    assert record.adversarial_check_scope == SCOPE_SYNTHETIC_OFFER_TEXT
    assert record.adversarial_digest == adversarial_digest(
        DISPOSITION_PASS,
        (),
        "No material counterparty objection detected.",
    )


def test_malformed_terms_are_refused():
    with pytest.raises(OfferRefused) as usd:
        evaluate_offer(**_valid_kwargs(offer_usd=-1))
    assert REASON_INVALID_OFFER_USD in usd.value.reasons

    with pytest.raises(OfferRefused) as term:
        evaluate_offer(**_valid_kwargs(term_months=0))
    assert REASON_INVALID_TERM in term.value.reasons

    with pytest.raises(OfferRefused) as level:
        evaluate_offer(**_valid_kwargs(commitment_level=9))
    assert REASON_INVALID_COMMITMENT_LEVEL in level.value.reasons

    with pytest.raises(OfferRefused) as disp:
        evaluate_offer(**_valid_kwargs(adversarial_disposition="LOOKS_FINE"))
    assert REASON_INVALID_ADVERSARIAL_DISPOSITION in disp.value.reasons


def test_write_appends_offer_chained_after_baseline():
    ledger = Ledger(aggregator=_unused_aggregator)
    baseline = dict(build_raw_event_payload("easy_save"))
    baseline["event_type"] = "baseline"
    ledger.append("evt-baseline-1", baseline)

    record = write_offer(ledger, "evt-offer-1", **_valid_kwargs())
    entries = ledger.entries
    assert len(entries) == 2
    assert entries[0]["event_id"] == "evt-baseline-1"
    assert entries[1]["event_id"] == "evt-offer-1"
    assert entries[1]["payload"]["event_type"] == "offer"
    assert entries[1]["payload"]["commitment_level"] == 2
    assert entries[1]["payload"]["adversarial_digest"] == record.adversarial_digest
    assert entries[1]["prev_hash"] == entries[0]["hash"]
    assert entries[1]["hash"] == chain_hash(entries[0]["hash"], entries[1]["payload"])
    assert ledger._chain_is_valid() is True


def test_refusal_does_not_append():
    ledger = Ledger(aggregator=_unused_aggregator)
    with pytest.raises(OfferRefused):
        write_offer(ledger, "evt-offer-1", **_valid_kwargs(offer_usd="forty-k"))
    assert ledger.entries == ()
