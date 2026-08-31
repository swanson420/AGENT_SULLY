"""Close path: baseline, one offer, settle or halt, export from the ledger."""

from __future__ import annotations

import json

from action.close_path import (
    BASELINE_EVENT_ID,
    HALT_EVENT_ID,
    OFFER_EVENT_ID,
    SETTLEMENT_EVENT_ID,
    close_path,
    export_json,
    run_all,
    witnessed_close_path,
)
from action.negotiation_driver import DriverDisposition
from action.offer import SCOPE_SYNTHETIC_OFFER_TEXT
from feedback.metrics import collect
from scenarios.vendor_renewal.scenario import (
    EXPECTED_EASY_SAVINGS_USD,
    MAX_TERM_MONTHS,
    TARGET_CEILING_USD,
)


def test_easy_save_close_path_exports_settlement():
    result = close_path("easy_save")
    export = result.export
    types = [event["event_type"] for event in export["events"]]

    assert result.disposition is DriverDisposition.SETTLED
    assert types == ["baseline", "offer", "offer_sent", "counterparty_reply", "settlement"]
    assert export["events"][0]["event_id"] == BASELINE_EVENT_ID
    assert export["events"][1]["event_id"] == OFFER_EVENT_ID
    assert export["events"][2]["payload"]["message"] == "offer sent"
    assert export["events"][3]["payload"]["disposition"] == "ACCEPT"
    assert export["events"][4]["event_id"] == SETTLEMENT_EVENT_ID
    assert export["events"][1]["prev_hash"] == export["events"][0]["hash"]
    assert export["events"][4]["prev_hash"] == export["events"][3]["hash"]
    assert export["commitment_trigger"] == "none"
    assert export["events"][1]["payload"]["commitment_level"] == 2
    assert export["events"][1]["payload"]["offer_usd"] == TARGET_CEILING_USD
    assert export["metrics"]["total_savings_usd"] == EXPECTED_EASY_SAVINGS_USD
    assert export["metrics"]["settlement_count"] == 1
    assert export["metrics"]["halt_count"] == 0
    assert result.metrics.total_savings_usd == EXPECTED_EASY_SAVINGS_USD


def test_constraint_conflict_close_path_exports_halt_not_savings():
    result = close_path(
        "constraint_conflict",
        offer_usd=TARGET_CEILING_USD,
        term_months=MAX_TERM_MONTHS,
    )
    export = result.export
    types = [event["event_type"] for event in export["events"]]

    assert result.disposition is DriverDisposition.HALTED_CONSTRAINT
    assert types == ["baseline", "offer", "offer_sent", "counterparty_reply", "halt"]
    assert export["events"][1]["event_id"] == OFFER_EVENT_ID
    assert export["events"][3]["payload"]["disposition"] == "COUNTER"
    assert export["events"][4]["event_id"] == HALT_EVENT_ID
    assert export["events"][4]["payload"]["human_required"] is True
    assert export["metrics"]["total_savings_usd"] == 0
    assert export["metrics"]["settlement_count"] == 0
    assert export["metrics"]["halt_count"] == 1
    assert "savings_usd" not in export["events"][3]["payload"]


def test_no_give_close_path_exports_halt():
    result = close_path("no_give")
    assert result.disposition is DriverDisposition.HALTED_REJECT
    assert [event["event_type"] for event in result.export["events"]] == [
        "baseline",
        "offer",
        "offer_sent",
        "counterparty_reply",
        "halt",
    ]
    assert result.export["metrics"]["total_savings_usd"] == 0


def test_export_matches_a_fresh_metrics_scan():
    result = close_path("easy_save")
    assert result.export["metrics"]["total_savings_usd"] == result.metrics.total_savings_usd
    packed = json.loads(export_json(result))
    assert packed["disposition"] == "SETTLED"
    assert packed["metrics"]["total_savings_usd"] == 8000


def test_run_all_covers_three_fixtures_without_sharing_ledgers():
    results = run_all()
    assert [item.fixture for item in results] == [
        "easy_save",
        "constraint_conflict",
        "no_give",
    ]
    assert results[0].metrics.total_savings_usd == 8000
    assert results[1].metrics.total_savings_usd == 0
    assert results[2].metrics.total_savings_usd == 0
    assert results[0].export is not results[1].export


def test_close_path_uses_real_classifier_not_a_stub():
    from action.close_path import OFFER_ACTION
    from action.commitment_gradient import classify_commitment_level
    from decision.contracts.blast_radius import BlastRadiusScore

    result = close_path("easy_save")
    expected = classify_commitment_level(
        OFFER_ACTION,
        BlastRadiusScore(
            reversibility="MEDIUM",
            cost="MEDIUM",
            relationship_impact="MEDIUM",
            commitment="MEDIUM",
            external_visibility="MEDIUM",
        ),
    )
    assert result.offer.commitment_level == expected == 2
    assert result.offer.adversarial_disposition == "PASS"
    assert result.offer.adversarial_check_scope == SCOPE_SYNTHETIC_OFFER_TEXT
    assert result.export["adversarial_check_scope"] == SCOPE_SYNTHETIC_OFFER_TEXT


def test_witnessed_path_uses_real_mutate_state_classifier():
    from action.commitment_gradient import classify_commitment_level
    from decision.contracts.blast_radius import BlastRadiusScore
    from decision.contracts.decision_package import ActionType

    result = witnessed_close_path("easy_save")
    expected = classify_commitment_level(
        ActionType.MUTATE_STATE,
        BlastRadiusScore(
            reversibility="MEDIUM",
            cost="MEDIUM",
            relationship_impact="MEDIUM",
            commitment="MEDIUM",
            external_visibility="MEDIUM",
        ),
    )
    types = [event["event_type"] for event in result.export["events"]]
    assert expected == 5
    assert result.offer.commitment_level == 5
    assert types[:5] == ["baseline", "human_ack", "offer", "offer_sent", "counterparty_reply"]
    assert result.export["commitment_trigger"] == "mandatory_escalation"
    assert result.export["adversarial_check_scope"] == SCOPE_SYNTHETIC_OFFER_TEXT
    assert result.offer.adversarial_disposition == "PASS"
    assert result.disposition.name == "SETTLED"
