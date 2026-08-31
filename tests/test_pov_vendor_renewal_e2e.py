"""PoV acceptance: vendor-renewal easy_save, full chain, real gates."""

from __future__ import annotations

from action.close_path import close_path
from action.commitment_gradient import classify_commitment_level
from action.negotiation_driver import DriverDisposition
from adversarial.sandbox_vendor import VendorDisposition, respond
from ledger.hash_chain import chain_hash
from scenarios.vendor_renewal.scenario import (
    BASELINE_USD,
    EXPECTED_EASY_SAVINGS_USD,
    MAX_TERM_MONTHS,
    TARGET_CEILING_USD,
    build_raw_event_payload,
)

EXPECTED_TYPES = (
    "baseline",
    "offer",
    "offer_sent",
    "counterparty_reply",
    "settlement",
)

CONSTRAINT_TYPES = (
    "baseline",
    "offer",
    "offer_sent",
    "counterparty_reply",
    "halt",
)


def _assert_contiguous_chain(events) -> None:
    assert events[0]["prev_hash"] == ""
    assert events[0]["hash"] == chain_hash("", events[0]["payload"])
    for index in range(1, len(events)):
        assert events[index]["prev_hash"] == events[index - 1]["hash"]
        assert events[index]["hash"] == chain_hash(
            events[index - 1]["hash"],
            events[index]["payload"],
        )


def test_easy_save_five_event_chain_and_positive_savings():
    result = close_path("easy_save")
    events = result.export["events"]
    types = tuple(event["event_type"] for event in events)

    assert result.disposition is DriverDisposition.SETTLED
    assert types == EXPECTED_TYPES
    assert len(events) == 5

    _assert_contiguous_chain(events)

    baseline = events[0]["payload"]
    offer = events[1]["payload"]
    sent = events[2]["payload"]
    reply = events[3]["payload"]
    settlement = events[4]["payload"]

    assert baseline["baseline_usd"] == BASELINE_USD
    assert offer["offer_usd"] == TARGET_CEILING_USD
    assert offer["term_months"] == MAX_TERM_MONTHS
    assert sent["message"] == "offer sent"
    assert reply["disposition"] == "ACCEPT"
    assert reply["offer_usd"] == TARGET_CEILING_USD
    assert settlement["closed_usd"] == TARGET_CEILING_USD
    assert settlement["constraint_honored"] is True
    assert settlement["savings_usd"] == EXPECTED_EASY_SAVINGS_USD
    assert settlement["savings_usd"] > 0
    assert settlement["savings_usd"] == baseline["baseline_usd"] - settlement["closed_usd"]

    payload = build_raw_event_payload("easy_save")
    plant_reply = respond(payload, TARGET_CEILING_USD, MAX_TERM_MONTHS)
    assert plant_reply.disposition is VendorDisposition.ACCEPT
    assert plant_reply.offer_usd == reply["offer_usd"]

    from action.close_path import OFFER_ACTION
    from decision.contracts.blast_radius import BlastRadiusScore

    expected_level = classify_commitment_level(
        OFFER_ACTION,
        BlastRadiusScore(
            reversibility="MEDIUM",
            cost="MEDIUM",
            relationship_impact="MEDIUM",
            commitment="MEDIUM",
            external_visibility="MEDIUM",
        ),
    )
    assert offer["commitment_level"] == expected_level
    assert result.export["adversarial_check_scope"] == "synthetic_offer_text"

    assert result.metrics.total_savings_usd == EXPECTED_EASY_SAVINGS_USD
    assert result.metrics.settlement_count == 1
    assert result.metrics.halt_count == 0
    assert result.metrics.total_savings_usd > 0


def test_constraint_conflict_halts_with_zero_ledger_savings():
    result = close_path("constraint_conflict")
    events = result.export["events"]
    types = tuple(event["event_type"] for event in events)

    assert result.disposition is DriverDisposition.HALTED_CONSTRAINT
    assert types == CONSTRAINT_TYPES
    _assert_contiguous_chain(events)

    reply = events[3]["payload"]
    halt = events[4]["payload"]
    payload = build_raw_event_payload("constraint_conflict")
    plant_reply = respond(payload, TARGET_CEILING_USD, MAX_TERM_MONTHS)

    assert plant_reply.disposition is VendorDisposition.COUNTER
    assert reply["disposition"] == "COUNTER"
    assert reply["offer_usd"] == plant_reply.offer_usd == 38000
    assert reply["term_months"] == plant_reply.term_months == 24
    assert halt["event_type"] == "halt"
    assert halt["human_required"] is True
    assert "savings_usd" not in halt
    assert all(event["event_type"] != "settlement" for event in events)

    assert result.metrics.total_savings_usd == 0
    assert result.metrics.settlement_count == 0
    assert result.metrics.halt_count == 1
    assert result.metrics.invalid_settlement_count == 0


def test_no_give_reject_halts_with_zero_ledger_savings():
    result = close_path("no_give")
    events = result.export["events"]
    types = tuple(event["event_type"] for event in events)

    assert result.disposition is DriverDisposition.HALTED_REJECT
    assert types == CONSTRAINT_TYPES
    _assert_contiguous_chain(events)

    reply = events[3]["payload"]
    halt = events[4]["payload"]
    payload = build_raw_event_payload("no_give")
    plant_reply = respond(payload, TARGET_CEILING_USD, MAX_TERM_MONTHS)

    assert plant_reply.disposition is VendorDisposition.REJECT
    assert reply["disposition"] == "REJECT"
    assert reply["offer_usd"] is None
    assert reply["term_months"] is None
    assert halt["event_type"] == "halt"
    assert halt["reason"] == "VENDOR_REJECT"
    assert halt["human_required"] is True
    assert "savings_usd" not in halt
    assert all(event["event_type"] != "settlement" for event in events)

    assert result.metrics.total_savings_usd == 0
    assert result.metrics.settlement_count == 0
    assert result.metrics.halt_count == 1
    assert result.metrics.invalid_settlement_count == 0
