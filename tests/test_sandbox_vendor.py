"""Sandbox vendor: scripted thresholds only. No invented concessions."""

from __future__ import annotations

import pytest

from action.settlement import (
    REASON_TERM_EXCEEDS_MAX,
    SettlementRefused,
    evaluate_settlement,
)
from adversarial.sandbox_vendor import (
    SandboxVendor,
    SandboxVendorError,
    VendorDisposition,
    respond,
)
from scenarios.vendor_renewal.scenario import (
    BASELINE_USD,
    MAX_TERM_MONTHS,
    TARGET_CEILING_USD,
    build_raw_event_payload,
)


def _payload(fixture: str):
    return build_raw_event_payload(fixture)


def test_easy_save_accepts_ceiling_and_twelve_months():
    reply = respond(_payload("easy_save"), TARGET_CEILING_USD, MAX_TERM_MONTHS)
    assert reply.disposition is VendorDisposition.ACCEPT
    assert reply.offer_usd == TARGET_CEILING_USD
    assert reply.term_months == MAX_TERM_MONTHS


def test_easy_save_accept_is_a_legal_settlement():
    reply = respond(_payload("easy_save"), TARGET_CEILING_USD, MAX_TERM_MONTHS)
    record = evaluate_settlement(
        baseline_usd=BASELINE_USD,
        closed_usd=reply.offer_usd,
        max_term_months=MAX_TERM_MONTHS,
        term_months=reply.term_months,
        target_ceiling_usd=TARGET_CEILING_USD,
    )
    assert record.savings_usd == 8000
    assert record.constraint_honored is True


def test_easy_save_rejects_below_floor_with_no_counter():
    reply = respond(_payload("easy_save"), TARGET_CEILING_USD - 1, MAX_TERM_MONTHS)
    assert reply.disposition is VendorDisposition.REJECT
    assert reply.offer_usd is None
    assert reply.term_months is None


def test_easy_save_rejects_term_above_required():
    reply = respond(_payload("easy_save"), TARGET_CEILING_USD, MAX_TERM_MONTHS + 1)
    assert reply.disposition is VendorDisposition.REJECT
    assert reply.offer_usd is None


def test_easy_save_does_not_invent_a_floor_counter():
    reply = respond(_payload("easy_save"), 35000, MAX_TERM_MONTHS)
    assert reply.disposition is VendorDisposition.REJECT
    assert reply.offer_usd != TARGET_CEILING_USD


def test_constraint_conflict_counters_only_the_scripted_24_month_deal():
    plant = _payload("constraint_conflict")["plant"]
    reply = respond(_payload("constraint_conflict"), TARGET_CEILING_USD, MAX_TERM_MONTHS)
    assert reply.disposition is VendorDisposition.COUNTER
    assert reply.offer_usd == plant["scripted_counter_usd"] == 38000
    assert reply.term_months == plant["scripted_counter_term_months"] == 24


def test_constraint_conflict_accepts_only_when_term_meets_required():
    reply = respond(_payload("constraint_conflict"), 38000, 24)
    assert reply.disposition is VendorDisposition.ACCEPT
    assert reply.offer_usd == 38000
    assert reply.term_months == 24


def test_constraint_conflict_scripted_counter_cannot_settle():
    reply = respond(_payload("constraint_conflict"), TARGET_CEILING_USD, 12)
    assert reply.disposition is VendorDisposition.COUNTER
    with pytest.raises(SettlementRefused) as caught:
        evaluate_settlement(
            baseline_usd=BASELINE_USD,
            closed_usd=reply.offer_usd,
            max_term_months=MAX_TERM_MONTHS,
            term_months=reply.term_months,
            target_ceiling_usd=TARGET_CEILING_USD,
        )
    assert REASON_TERM_EXCEEDS_MAX in caught.value.reasons


def test_no_give_rejects_any_price_below_baseline():
    reply = respond(_payload("no_give"), TARGET_CEILING_USD, MAX_TERM_MONTHS)
    assert reply.disposition is VendorDisposition.REJECT
    assert reply.offer_usd is None
    assert reply.term_months is None


def test_no_give_accepts_baseline_without_inventing_a_discount():
    reply = respond(_payload("no_give"), BASELINE_USD, MAX_TERM_MONTHS)
    assert reply.disposition is VendorDisposition.ACCEPT
    assert reply.offer_usd == BASELINE_USD


def test_missing_plant_does_not_default_a_policy():
    with pytest.raises(SandboxVendorError):
        respond({"scenario": "vendor-renewal"}, TARGET_CEILING_USD, MAX_TERM_MONTHS)


def test_unknown_policy_does_not_guess():
    payload = {
        "plant": {
            "sandbox_vendor_floor_usd": 40000,
            "sandbox_vendor_required_term_months": 12,
            "sandbox_vendor_policy": "be_nice_and_meet_in_the_middle",
            "scripted_counter_usd": None,
            "scripted_counter_term_months": None,
        }
    }
    with pytest.raises(SandboxVendorError):
        respond(payload, 42000, 12)


def test_wrapper_matches_function():
    vendor = SandboxVendor()
    payload = _payload("easy_save")
    assert vendor.respond(payload, 40000, 12) == respond(payload, 40000, 12)
