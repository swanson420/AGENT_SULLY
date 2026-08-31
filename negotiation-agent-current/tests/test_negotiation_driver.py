"""Driver: settle only a valid plant accept. Halt writes a halt, not a settlement."""

from __future__ import annotations

from action.halt import REASON_CONSTRAINT, REASON_VENDOR_REJECT
from action.negotiation_driver import DriverDisposition, drive
from action.settlement import REASON_CLOSED_EXCEEDS_CEILING, REASON_TERM_EXCEEDS_MAX
from adversarial.sandbox_vendor import VendorDisposition
from scenarios.vendor_renewal.scenario import (
    BASELINE_USD,
    EXPECTED_EASY_SAVINGS_USD,
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


def test_easy_save_accept_writes_settlement():
    ledger = RecordingLedger()
    result = drive(
        build_raw_event_payload("easy_save"),
        TARGET_CEILING_USD,
        MAX_TERM_MONTHS,
        ledger=ledger,
        settlement_event_id="evt-settle-easy",
        evidence_event_ids=("evt-baseline-1",),
    )
    assert result.disposition is DriverDisposition.SETTLED
    assert result.vendor_reply.disposition is VendorDisposition.ACCEPT
    assert result.settlement is not None
    assert result.settlement.savings_usd == EXPECTED_EASY_SAVINGS_USD
    assert [item[1]["event_type"] for item in ledger.appended] == [
        "counterparty_reply",
        "settlement",
    ]
    assert ledger.appended[1][0] == "evt-settle-easy"
    assert ledger.appended[1][1]["savings_usd"] == 8000


def test_easy_save_reject_writes_halt_not_settlement():
    ledger = RecordingLedger()
    result = drive(
        build_raw_event_payload("easy_save"),
        TARGET_CEILING_USD - 1,
        MAX_TERM_MONTHS,
        ledger=ledger,
        halt_event_id="evt-halt-1",
    )
    assert result.disposition is DriverDisposition.HALTED_REJECT
    assert result.settlement is None
    assert result.halt is not None
    assert result.halt.reason == REASON_VENDOR_REJECT
    assert result.halt.human_required is True
    assert [item[1]["event_type"] for item in ledger.appended] == [
        "counterparty_reply",
        "halt",
    ]
    assert ledger.appended[1][0] == "evt-halt-1"
    assert ledger.appended[1][1]["reason"] == REASON_VENDOR_REJECT


def test_constraint_conflict_counter_halts_before_write():
    ledger = RecordingLedger()
    result = drive(
        build_raw_event_payload("constraint_conflict"),
        TARGET_CEILING_USD,
        MAX_TERM_MONTHS,
        ledger=ledger,
    )
    assert result.vendor_reply.disposition is VendorDisposition.COUNTER
    assert result.vendor_reply.term_months == 24
    assert result.disposition is DriverDisposition.HALTED_CONSTRAINT
    assert REASON_TERM_EXCEEDS_MAX in result.refusal_reasons
    assert result.settlement is None
    assert result.halt is not None
    assert result.halt.reason == REASON_CONSTRAINT
    assert result.halt.human_required is True
    assert REASON_TERM_EXCEEDS_MAX in result.halt.detail_codes
    assert [item[1]["event_type"] for item in ledger.appended] == [
        "counterparty_reply",
        "halt",
    ]
    assert ledger.appended[1][1]["reason"] == REASON_CONSTRAINT


def test_constraint_conflict_vendor_accept_of_24_month_term_does_not_settle():
    """WATCH: incoming reply that fails constraints must not emit settlement."""
    ledger = RecordingLedger()
    result = drive(
        build_raw_event_payload("constraint_conflict"),
        38000,
        24,
        ledger=ledger,
    )
    assert result.vendor_reply.disposition is VendorDisposition.ACCEPT
    assert result.disposition is DriverDisposition.HALTED_CONSTRAINT
    assert REASON_TERM_EXCEEDS_MAX in result.refusal_reasons
    assert result.settlement is None
    assert result.halt is not None
    assert result.halt.reason == REASON_CONSTRAINT
    assert ledger.appended[0][1]["event_type"] == "counterparty_reply"
    assert ledger.appended[1][1]["event_type"] == "halt"
    assert "savings_usd" not in ledger.appended[1][1]


def test_no_give_reject_writes_halt_not_settlement():
    ledger = RecordingLedger()
    result = drive(
        build_raw_event_payload("no_give"),
        TARGET_CEILING_USD,
        MAX_TERM_MONTHS,
        ledger=ledger,
    )
    assert result.disposition is DriverDisposition.HALTED_REJECT
    assert result.settlement is None
    assert ledger.appended[0][1]["event_type"] == "counterparty_reply"
    assert ledger.appended[1][1]["event_type"] == "halt"
    assert ledger.appended[1][1]["human_required"] is True


def test_no_give_accept_at_baseline_fails_ceiling_and_writes_nothing():
    ledger = RecordingLedger()
    result = drive(
        build_raw_event_payload("no_give"),
        BASELINE_USD,
        MAX_TERM_MONTHS,
        ledger=ledger,
    )
    assert result.vendor_reply.disposition is VendorDisposition.ACCEPT
    assert result.disposition is DriverDisposition.HALTED_CONSTRAINT
    assert REASON_CLOSED_EXCEEDS_CEILING in result.refusal_reasons
    assert result.settlement is None
    assert result.halt.reason == REASON_CONSTRAINT
    assert ledger.appended[0][1]["event_type"] == "counterparty_reply"
    assert ledger.appended[1][1]["event_type"] == "halt"
    assert REASON_CLOSED_EXCEEDS_CEILING in result.halt.detail_codes
