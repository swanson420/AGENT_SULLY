"""Metrics read model: scan validated payloads only. No cached totals."""

from __future__ import annotations

from action.halt import (
    ALLOWED_DETAIL_CODES,
    ALLOWED_HALT_REASONS,
    REASON_CONSTRAINT,
    REASON_VENDOR_COUNTER,
    REASON_VENDOR_REJECT,
    write_halt,
)
from action.negotiation_driver import drive
from action.settlement import (
    REASON_CLOSED_EXCEEDS_CEILING,
    REASON_FORBIDDEN_TERM,
    REASON_TERM_EXCEEDS_MAX,
    write_settlement,
)
from feedback.metrics import (
    baseline_count,
    collect,
    constraint_by_detail,
    halt_by_reason,
    halt_count,
    settlement_count,
    total_savings_usd,
)
from ledger.ledger import Ledger
from scenarios.vendor_renewal.scenario import (
    BASELINE_USD,
    MAX_TERM_MONTHS,
    TARGET_CEILING_USD,
    build_raw_event_payload,
)


def _unused_aggregator(event_ids, lookup):
    return {}, ""


def _ledger() -> Ledger:
    return Ledger(aggregator=_unused_aggregator)


def test_empty_ledger_is_zero():
    snap = collect(_ledger())
    assert snap.baseline_count == 0
    assert snap.settlement_count == 0
    assert snap.invalid_settlement_count == 0
    assert snap.halt_count == 0
    assert snap.invalid_halt_count == 0
    assert snap.halt_by_reason == {reason: 0 for reason in sorted(ALLOWED_HALT_REASONS)}
    assert snap.constraint_by_detail == {code: 0 for code in sorted(ALLOWED_DETAIL_CODES)}
    assert snap.total_savings_usd == 0


def test_baseline_only_halt_adds_no_savings():
    ledger = _ledger()
    payload = dict(build_raw_event_payload("easy_save"))
    payload["event_type"] = "baseline"
    ledger.append("evt-baseline-1", payload)
    drive(
        payload,
        TARGET_CEILING_USD - 1,
        MAX_TERM_MONTHS,
        ledger=ledger,
        settlement_event_id="evt-settlement-1",
    )
    snap = collect(ledger)
    assert snap.baseline_count == 1
    assert snap.settlement_count == 0
    assert snap.halt_count == 1
    assert snap.invalid_halt_count == 0
    assert snap.total_savings_usd == 0
    assert total_savings_usd(ledger) == 0
    assert halt_count(ledger) == 1


def test_easy_save_settlement_counts_verified_savings():
    ledger = _ledger()
    payload = dict(build_raw_event_payload("easy_save"))
    payload["event_type"] = "baseline"
    ledger.append("evt-baseline-1", payload)
    drive(
        payload,
        TARGET_CEILING_USD,
        MAX_TERM_MONTHS,
        ledger=ledger,
        settlement_event_id="evt-settlement-1",
    )
    snap = collect(ledger)
    assert snap.baseline_count == 1
    assert snap.settlement_count == 1
    assert snap.invalid_settlement_count == 0
    assert snap.total_savings_usd == 8000
    assert settlement_count(ledger) == 1
    assert baseline_count(ledger) == 1


def test_forged_settlement_payload_is_not_counted_as_savings():
    ledger = _ledger()
    ledger.append(
        "evt-forged",
        {
            "event_type": "settlement",
            "baseline_usd": BASELINE_USD,
            "closed_usd": 38000,
            "savings_usd": 10000,
            "max_term_months": MAX_TERM_MONTHS,
            "term_months": 24,
            "target_ceiling_usd": TARGET_CEILING_USD,
            "constraint_honored": True,
            "forbidden_terms": (),
            "accepted_terms": (),
        },
    )
    snap = collect(ledger)
    assert snap.settlement_count == 0
    assert snap.invalid_settlement_count == 1
    assert snap.total_savings_usd == 0


def test_savings_mismatch_is_invalid_not_a_save():
    ledger = _ledger()
    write_settlement(
        ledger,
        "evt-real",
        baseline_usd=BASELINE_USD,
        closed_usd=TARGET_CEILING_USD,
        max_term_months=MAX_TERM_MONTHS,
        term_months=MAX_TERM_MONTHS,
        target_ceiling_usd=TARGET_CEILING_USD,
    )
    # Corrupt the stored savings after a legal write. Collect must
    # rescan and refuse the mutated payload instead of trusting memory.
    ledger._entries[0]["payload"]["savings_usd"] = 99999
    snap = collect(ledger)
    assert snap.settlement_count == 0
    assert snap.invalid_settlement_count == 1
    assert snap.total_savings_usd == 0


def test_collect_has_no_running_total_across_calls():
    ledger = _ledger()
    first = collect(ledger)
    payload = dict(build_raw_event_payload("easy_save"))
    payload["event_type"] = "baseline"
    ledger.append("evt-baseline-1", payload)
    drive(
        payload,
        TARGET_CEILING_USD,
        MAX_TERM_MONTHS,
        ledger=ledger,
        settlement_event_id="evt-settlement-1",
    )
    second = collect(ledger)
    assert first.total_savings_usd == 0
    assert second.total_savings_usd == 8000
    assert first is not second


def test_verified_halt_is_counted():
    ledger = _ledger()
    write_halt(
        ledger,
        "evt-halt-1",
        reason=REASON_VENDOR_REJECT,
        human_required=True,
    )
    snap = collect(ledger)
    assert snap.halt_count == 1
    assert snap.invalid_halt_count == 0
    assert snap.halt_by_reason[REASON_VENDOR_REJECT] == 1
    assert snap.halt_by_reason[REASON_VENDOR_COUNTER] == 0
    assert snap.halt_by_reason[REASON_CONSTRAINT] == 0
    assert snap.constraint_by_detail[REASON_TERM_EXCEEDS_MAX] == 0
    assert snap.total_savings_usd == 0


def test_unknown_halt_reason_is_invalid():
    ledger = _ledger()
    ledger.append(
        "evt-forged-halt",
        {
            "event_type": "halt",
            "reason": "LOOKS_FINE_OVERRIDE",
            "detail_codes": (),
            "human_required": True,
            "evidence_event_ids": (),
            "vendor_id": None,
            "fixture": None,
        },
    )
    snap = collect(ledger)
    assert snap.halt_count == 0
    assert snap.invalid_halt_count == 1
    assert snap.halt_by_reason[REASON_VENDOR_REJECT] == 0
    assert snap.halt_by_reason[REASON_VENDOR_COUNTER] == 0
    assert snap.halt_by_reason[REASON_CONSTRAINT] == 0


def test_constraint_halt_without_detail_codes_is_invalid():
    ledger = _ledger()
    ledger.append(
        "evt-bare-constraint",
        {
            "event_type": "halt",
            "reason": REASON_CONSTRAINT,
            "detail_codes": (),
            "human_required": True,
            "evidence_event_ids": (),
            "vendor_id": None,
            "fixture": None,
        },
    )
    snap = collect(ledger)
    assert snap.halt_count == 0
    assert snap.invalid_halt_count == 1


def test_constraint_halt_with_unallowlisted_detail_is_invalid():
    ledger = _ledger()
    ledger.append(
        "evt-bad-detail",
        {
            "event_type": "halt",
            "reason": REASON_CONSTRAINT,
            "detail_codes": ("MADE_UP_CODE",),
            "human_required": True,
            "evidence_event_ids": (),
            "vendor_id": None,
            "fixture": None,
        },
    )
    snap = collect(ledger)
    assert snap.halt_count == 0
    assert snap.invalid_halt_count == 1


def test_mutated_halt_reason_is_invalid_on_rescan():
    ledger = _ledger()
    write_halt(
        ledger,
        "evt-halt-1",
        reason=REASON_CONSTRAINT,
        detail_codes=(REASON_TERM_EXCEEDS_MAX,),
        human_required=True,
    )
    ledger._entries[0]["payload"]["reason"] = "LOOKS_FINE_OVERRIDE"
    snap = collect(ledger)
    assert snap.halt_count == 0
    assert snap.invalid_halt_count == 1
    assert snap.halt_by_reason[REASON_CONSTRAINT] == 0
    assert snap.constraint_by_detail[REASON_TERM_EXCEEDS_MAX] == 0


def test_halt_reasons_bucket_independently_on_each_scan():
    ledger = _ledger()
    write_halt(ledger, "evt-h1", reason=REASON_VENDOR_REJECT, human_required=True)
    write_halt(ledger, "evt-h2", reason=REASON_VENDOR_COUNTER, human_required=True)
    write_halt(
        ledger,
        "evt-h3",
        reason=REASON_CONSTRAINT,
        detail_codes=(REASON_TERM_EXCEEDS_MAX,),
        human_required=True,
    )
    write_halt(ledger, "evt-h4", reason=REASON_VENDOR_REJECT, human_required=True)
    first = collect(ledger)
    second = collect(ledger)
    assert first.halt_count == 4
    assert first.halt_by_reason[REASON_VENDOR_REJECT] == 2
    assert first.halt_by_reason[REASON_VENDOR_COUNTER] == 1
    assert first.halt_by_reason[REASON_CONSTRAINT] == 1
    assert sum(first.halt_by_reason.values()) == first.halt_count
    assert dict(second.halt_by_reason) == dict(first.halt_by_reason)
    assert first.halt_by_reason is not second.halt_by_reason
    assert halt_by_reason(ledger)[REASON_VENDOR_REJECT] == 2


def test_halt_by_reason_view_is_immutable():
    snap = collect(_ledger())
    try:
        snap.halt_by_reason[REASON_VENDOR_REJECT] = 99
    except TypeError:
        return
    raise AssertionError("halt_by_reason must not accept mutation")


def test_constraint_details_bucket_from_revalidated_codes_only():
    ledger = _ledger()
    write_halt(ledger, "evt-reject", reason=REASON_VENDOR_REJECT, human_required=True)
    write_halt(
        ledger,
        "evt-c1",
        reason=REASON_CONSTRAINT,
        detail_codes=(REASON_TERM_EXCEEDS_MAX,),
        human_required=True,
    )
    write_halt(
        ledger,
        "evt-c2",
        reason=REASON_CONSTRAINT,
        detail_codes=(REASON_TERM_EXCEEDS_MAX, REASON_CLOSED_EXCEEDS_CEILING),
        human_required=True,
    )
    first = collect(ledger)
    second = collect(ledger)
    assert first.halt_by_reason[REASON_CONSTRAINT] == 2
    assert first.constraint_by_detail[REASON_TERM_EXCEEDS_MAX] == 2
    assert first.constraint_by_detail[REASON_CLOSED_EXCEEDS_CEILING] == 1
    assert first.constraint_by_detail[REASON_FORBIDDEN_TERM] == 0
    assert dict(second.constraint_by_detail) == dict(first.constraint_by_detail)
    assert first.constraint_by_detail is not second.constraint_by_detail
    assert constraint_by_detail(ledger)[REASON_TERM_EXCEEDS_MAX] == 2


def test_invalid_constraint_payload_does_not_fill_detail_buckets():
    ledger = _ledger()
    ledger.append(
        "evt-bad-detail",
        {
            "event_type": "halt",
            "reason": REASON_CONSTRAINT,
            "detail_codes": ("MADE_UP_CODE",),
            "human_required": True,
            "evidence_event_ids": (),
            "vendor_id": None,
            "fixture": None,
        },
    )
    snap = collect(ledger)
    assert snap.invalid_halt_count == 1
    assert all(value == 0 for value in snap.constraint_by_detail.values())


def test_constraint_by_detail_view_is_immutable():
    snap = collect(_ledger())
    try:
        snap.constraint_by_detail[REASON_TERM_EXCEEDS_MAX] = 99
    except TypeError:
        return
    raise AssertionError("constraint_by_detail must not accept mutation")
