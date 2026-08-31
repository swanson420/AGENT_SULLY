"""Settlement writer: verified savings or refusal. No illegal close writes."""

from __future__ import annotations

import pytest

from action.settlement import (
    REASON_CLOSED_EXCEEDS_BASELINE,
    REASON_CLOSED_EXCEEDS_CEILING,
    REASON_FORBIDDEN_TERM,
    REASON_TERM_EXCEEDS_MAX,
    SettlementRecord,
    SettlementRefused,
    evaluate_settlement,
    write_settlement,
)
from scenarios.vendor_renewal.scenario import (
    BASELINE_USD,
    EXPECTED_EASY_SAVINGS_USD,
    FORBIDDEN_TERMS,
    MAX_TERM_MONTHS,
    TARGET_CEILING_USD,
    build_raw_event_payload,
)


class RecordingLedger:
    def __init__(self) -> None:
        self.appended = []

    def append(self, event_id, payload):
        self.appended.append((event_id, payload))
        return "hash"


def _easy_kwargs(**overrides):
    payload = build_raw_event_payload("easy_save")
    kwargs = dict(
        baseline_usd=payload["baseline_usd"],
        closed_usd=payload["reference"]["expected_closed_usd"],
        max_term_months=payload["max_term_months"],
        term_months=payload["reference"]["expected_term_months"],
        target_ceiling_usd=payload["target_ceiling_usd"],
        forbidden_terms=payload["forbidden_terms"],
        accepted_terms=(),
        evidence_event_ids=("evt-baseline-1",),
        vendor_id=payload["vendor_id"],
        sku=payload["sku"],
        currency=payload["currency"],
        fixture=payload["fixture"],
    )
    kwargs.update(overrides)
    return kwargs


def test_easy_save_computes_verified_savings():
    record = evaluate_settlement(**_easy_kwargs())
    assert isinstance(record, SettlementRecord)
    assert record.constraint_honored is True
    assert record.baseline_usd == BASELINE_USD
    assert record.closed_usd == TARGET_CEILING_USD
    assert record.term_months == MAX_TERM_MONTHS
    assert record.savings_usd == EXPECTED_EASY_SAVINGS_USD == 8000
    assert record.event_type == "settlement"


def test_refuses_closed_cost_above_baseline():
    with pytest.raises(SettlementRefused) as caught:
        evaluate_settlement(**_easy_kwargs(closed_usd=BASELINE_USD + 1))
    assert REASON_CLOSED_EXCEEDS_BASELINE in caught.value.reasons


def test_refuses_term_above_max_months():
    with pytest.raises(SettlementRefused) as caught:
        evaluate_settlement(**_easy_kwargs(term_months=MAX_TERM_MONTHS + 1))
    assert REASON_TERM_EXCEEDS_MAX in caught.value.reasons


def test_constraint_conflict_price_cut_with_24_month_term_is_refused():
    payload = build_raw_event_payload("constraint_conflict")
    with pytest.raises(SettlementRefused) as caught:
        evaluate_settlement(
            baseline_usd=payload["baseline_usd"],
            closed_usd=payload["plant"]["scripted_counter_usd"],
            max_term_months=payload["max_term_months"],
            term_months=payload["plant"]["scripted_counter_term_months"],
            target_ceiling_usd=payload["target_ceiling_usd"],
            forbidden_terms=payload["forbidden_terms"],
            fixture=payload["fixture"],
        )
    assert REASON_TERM_EXCEEDS_MAX in caught.value.reasons
    # Price is below baseline, so this is not a baseline-spend failure.
    assert REASON_CLOSED_EXCEEDS_BASELINE not in caught.value.reasons


def test_reports_both_hard_failures_together():
    with pytest.raises(SettlementRefused) as caught:
        evaluate_settlement(
            baseline_usd=BASELINE_USD,
            closed_usd=BASELINE_USD + 5000,
            max_term_months=MAX_TERM_MONTHS,
            term_months=24,
        )
    assert REASON_CLOSED_EXCEEDS_BASELINE in caught.value.reasons
    assert REASON_TERM_EXCEEDS_MAX in caught.value.reasons


def test_zero_savings_at_baseline_is_legal_but_not_a_price_win():
    record = evaluate_settlement(
        baseline_usd=BASELINE_USD,
        closed_usd=BASELINE_USD,
        max_term_months=MAX_TERM_MONTHS,
        term_months=MAX_TERM_MONTHS,
        target_ceiling_usd=None,
    )
    assert record.savings_usd == 0
    assert record.constraint_honored is True


def test_closed_above_ceiling_but_below_baseline_is_still_refused():
    with pytest.raises(SettlementRefused) as caught:
        evaluate_settlement(**_easy_kwargs(closed_usd=45000))
    assert REASON_CLOSED_EXCEEDS_CEILING in caught.value.reasons
    assert REASON_CLOSED_EXCEEDS_BASELINE not in caught.value.reasons


def test_forbidden_term_on_accepted_close_is_refused():
    with pytest.raises(SettlementRefused) as caught:
        evaluate_settlement(
            **_easy_kwargs(accepted_terms=("auto-renew-expansion",))
        )
    assert REASON_FORBIDDEN_TERM in caught.value.reasons
    assert "auto-renew-expansion" in FORBIDDEN_TERMS


def test_write_appends_only_after_evaluation_passes():
    ledger = RecordingLedger()
    record = write_settlement(ledger, "evt-settle-1", **_easy_kwargs())
    assert len(ledger.appended) == 1
    event_id, payload = ledger.appended[0]
    assert event_id == "evt-settle-1"
    assert payload["savings_usd"] == 8000
    assert payload["constraint_honored"] is True
    assert record.to_payload() == payload


def test_write_does_not_append_on_refusal():
    ledger = RecordingLedger()
    with pytest.raises(SettlementRefused):
        write_settlement(
            ledger,
            "evt-settle-bad",
            **_easy_kwargs(term_months=24, closed_usd=38000),
        )
    assert ledger.appended == []
