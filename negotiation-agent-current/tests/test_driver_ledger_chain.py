"""Concrete ledger chain: baseline then settlement, or baseline alone.

Success is exactly two hash-linked entries. Every halted outcome must
leave the ledger with only the baseline that was appended before drive().
"""

from __future__ import annotations

from action.negotiation_driver import DriverDisposition, drive
from ledger.hash_chain import chain_hash
from ledger.ledger import Ledger
from scenarios.vendor_renewal.scenario import (
    BASELINE_USD,
    MAX_TERM_MONTHS,
    TARGET_CEILING_USD,
    build_raw_event_payload,
)

BASELINE_EVENT_ID = "evt-baseline-1"
SETTLEMENT_EVENT_ID = "evt-settlement-1"


def _unused_aggregator(event_ids, lookup):
    """Append/get_event do not call the aggregator. Injected so Ledger
    construction does not import triage_gate — out of scope for this loop."""
    return {}, ""


def _seed_baseline(fixture: str) -> tuple[Ledger, dict]:
    payload = dict(build_raw_event_payload(fixture))
    payload["event_type"] = "baseline"
    ledger = Ledger(aggregator=_unused_aggregator)
    ledger.append(BASELINE_EVENT_ID, payload)
    return ledger, payload


HALT_EVENT_ID = "evt-halt-1"


def _assert_baseline_then_halt(ledger: Ledger, baseline_before) -> None:
    entries = ledger.entries
    assert len(entries) == 3
    baseline, reply, halt = entries
    assert baseline["event_id"] == BASELINE_EVENT_ID
    assert baseline["payload"]["event_type"] == "baseline"
    assert baseline["payload"] == baseline_before["payload"]
    assert baseline["hash"] == baseline_before["hash"]
    assert reply["payload"]["event_type"] == "counterparty_reply"
    assert halt["event_id"] == HALT_EVENT_ID
    assert halt["payload"]["event_type"] == "halt"
    assert halt["payload"]["human_required"] is True
    assert reply["prev_hash"] == baseline["hash"]
    assert halt["prev_hash"] == reply["hash"]
    assert halt["hash"] == chain_hash(reply["hash"], halt["payload"])
    assert ledger.get_event(SETTLEMENT_EVENT_ID) is None
    assert ledger._chain_is_valid() is True


def test_easy_save_appends_settlement_as_second_chained_entry():
    ledger, payload = _seed_baseline("easy_save")
    result = drive(
        payload,
        TARGET_CEILING_USD,
        MAX_TERM_MONTHS,
        ledger=ledger,
        settlement_event_id=SETTLEMENT_EVENT_ID,
        evidence_event_ids=(BASELINE_EVENT_ID,),
    )

    assert result.disposition is DriverDisposition.SETTLED
    entries = ledger.entries
    assert len(entries) == 3

    baseline, reply, settlement = entries
    assert baseline["event_id"] == BASELINE_EVENT_ID
    assert baseline["payload"]["event_type"] == "baseline"
    assert baseline["prev_hash"] == ""
    assert reply["payload"]["event_type"] == "counterparty_reply"
    assert reply["payload"]["disposition"] == "ACCEPT"

    assert settlement["event_id"] == SETTLEMENT_EVENT_ID
    assert settlement["payload"]["event_type"] == "settlement"
    assert settlement["payload"]["savings_usd"] == 8000
    assert settlement["payload"]["constraint_honored"] is True
    assert reply["prev_hash"] == baseline["hash"]
    assert settlement["prev_hash"] == reply["hash"]
    assert settlement["hash"] == chain_hash(reply["hash"], settlement["payload"])
    assert ledger._chain_is_valid() is True


def test_easy_save_reject_appends_halt_without_touching_baseline():
    ledger, payload = _seed_baseline("easy_save")
    before = ledger.get_event(BASELINE_EVENT_ID)
    result = drive(
        payload,
        TARGET_CEILING_USD - 1,
        MAX_TERM_MONTHS,
        ledger=ledger,
        settlement_event_id=SETTLEMENT_EVENT_ID,
        halt_event_id=HALT_EVENT_ID,
        evidence_event_ids=(BASELINE_EVENT_ID,),
    )
    assert result.disposition is DriverDisposition.HALTED_REJECT
    _assert_baseline_then_halt(ledger, before)


def test_constraint_conflict_counter_appends_halt_without_touching_baseline():
    ledger, payload = _seed_baseline("constraint_conflict")
    before = ledger.get_event(BASELINE_EVENT_ID)
    result = drive(
        payload,
        TARGET_CEILING_USD,
        MAX_TERM_MONTHS,
        ledger=ledger,
        settlement_event_id=SETTLEMENT_EVENT_ID,
        halt_event_id=HALT_EVENT_ID,
        evidence_event_ids=(BASELINE_EVENT_ID,),
    )
    assert result.disposition is DriverDisposition.HALTED_CONSTRAINT
    _assert_baseline_then_halt(ledger, before)


def test_constraint_conflict_illegal_accept_appends_halt_without_touching_baseline():
    ledger, payload = _seed_baseline("constraint_conflict")
    before = ledger.get_event(BASELINE_EVENT_ID)
    result = drive(
        payload,
        38000,
        24,
        ledger=ledger,
        settlement_event_id=SETTLEMENT_EVENT_ID,
        halt_event_id=HALT_EVENT_ID,
        evidence_event_ids=(BASELINE_EVENT_ID,),
    )
    assert result.disposition is DriverDisposition.HALTED_CONSTRAINT
    _assert_baseline_then_halt(ledger, before)


def test_no_give_reject_appends_halt_without_touching_baseline():
    ledger, payload = _seed_baseline("no_give")
    before = ledger.get_event(BASELINE_EVENT_ID)
    result = drive(
        payload,
        TARGET_CEILING_USD,
        MAX_TERM_MONTHS,
        ledger=ledger,
        settlement_event_id=SETTLEMENT_EVENT_ID,
        halt_event_id=HALT_EVENT_ID,
        evidence_event_ids=(BASELINE_EVENT_ID,),
    )
    assert result.disposition is DriverDisposition.HALTED_REJECT
    _assert_baseline_then_halt(ledger, before)


def test_no_give_baseline_accept_fails_ceiling_and_appends_halt():
    ledger, payload = _seed_baseline("no_give")
    before = ledger.get_event(BASELINE_EVENT_ID)
    result = drive(
        payload,
        BASELINE_USD,
        MAX_TERM_MONTHS,
        ledger=ledger,
        settlement_event_id=SETTLEMENT_EVENT_ID,
        halt_event_id=HALT_EVENT_ID,
        evidence_event_ids=(BASELINE_EVENT_ID,),
    )
    assert result.disposition is DriverDisposition.HALTED_CONSTRAINT
    _assert_baseline_then_halt(ledger, before)
