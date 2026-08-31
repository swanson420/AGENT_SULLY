"""Halt writer: verified codes only. Baseline entry is not rewritten."""

from __future__ import annotations

import pytest

from action.halt import (
    ALLOWED_HALT_REASONS,
    HaltRefused,
    REASON_CONSTRAINT,
    REASON_VENDOR_REJECT,
    evaluate_halt,
    write_halt,
)
from action.settlement import REASON_TERM_EXCEEDS_MAX
from ledger.hash_chain import chain_hash
from ledger.ledger import Ledger
from scenarios.vendor_renewal.scenario import build_raw_event_payload


def _unused_aggregator(event_ids, lookup):
    return {}, ""


def test_evaluate_accepts_only_allowlisted_reasons():
    record = evaluate_halt(reason=REASON_VENDOR_REJECT, human_required=True)
    assert record.event_type == "halt"
    assert record.reason == REASON_VENDOR_REJECT
    assert record.human_required is True
    assert record.reason in ALLOWED_HALT_REASONS


def test_unknown_reason_is_refused_and_not_written():
    ledger = Ledger(aggregator=_unused_aggregator)
    with pytest.raises(HaltRefused):
        write_halt(ledger, "evt-halt-1", reason="LOOKS_FINE_OVERRIDE")
    assert ledger.entries == ()


def test_constraint_requires_verified_detail_codes():
    with pytest.raises(HaltRefused):
        evaluate_halt(reason=REASON_CONSTRAINT, detail_codes=())
    with pytest.raises(HaltRefused):
        evaluate_halt(
            reason=REASON_CONSTRAINT,
            detail_codes=("MADE_UP_CODE",),
        )


def test_write_appends_halt_without_changing_baseline():
    ledger = Ledger(aggregator=_unused_aggregator)
    baseline = dict(build_raw_event_payload("easy_save"))
    baseline["event_type"] = "baseline"
    ledger.append("evt-baseline-1", baseline)
    before = ledger.get_event("evt-baseline-1")

    record = write_halt(
        ledger,
        "evt-halt-1",
        reason=REASON_CONSTRAINT,
        detail_codes=(REASON_TERM_EXCEEDS_MAX,),
        human_required=True,
        evidence_event_ids=("evt-baseline-1",),
    )
    after = ledger.get_event("evt-baseline-1")
    entries = ledger.entries

    assert after["payload"] == before["payload"]
    assert after["hash"] == before["hash"]
    assert len(entries) == 2
    assert entries[0]["event_id"] == "evt-baseline-1"
    assert entries[1]["event_id"] == "evt-halt-1"
    assert entries[1]["payload"]["event_type"] == "halt"
    assert entries[1]["payload"]["reason"] == REASON_CONSTRAINT
    assert tuple(entries[1]["payload"]["detail_codes"]) == (REASON_TERM_EXCEEDS_MAX,)
    assert entries[1]["payload"]["human_required"] is True
    assert entries[1]["prev_hash"] == entries[0]["hash"]
    assert entries[1]["hash"] == chain_hash(entries[0]["hash"], entries[1]["payload"])
    assert record.human_required is True
    assert ledger._chain_is_valid() is True
