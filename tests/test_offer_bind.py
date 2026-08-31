"""Wrapper forwards evaluated signals and leaves offer terms untouched."""

from __future__ import annotations

from types import SimpleNamespace

from action.offer import DISPOSITION_BOUNCE_DOMAIN, DISPOSITION_PASS
from action.offer_bind import bind_and_write_offer
from ledger.ledger import Ledger
from scenarios.vendor_renewal.scenario import MAX_TERM_MONTHS, TARGET_CEILING_USD


def _unused_aggregator(event_ids, lookup):
    return {}, ""


def _ledger() -> Ledger:
    return Ledger(aggregator=_unused_aggregator)


def test_wrapper_writes_classifier_and_assessment_verbatim():
    seen = {}

    def classify(action, blast):
        seen["classify"] = (action, blast)
        return 2

    def assess(record):
        seen["assess"] = record
        return SimpleNamespace(
            disposition=SimpleNamespace(name=DISPOSITION_PASS),
            objections=(),
            rationale="No material counterparty objection detected.",
        )

    action = object()
    blast = object()
    record = object()
    ledger = _ledger()

    written = bind_and_write_offer(
        ledger,
        "evt-offer-1",
        offer_usd=TARGET_CEILING_USD,
        term_months=MAX_TERM_MONTHS,
        classify_fn=classify,
        assess_fn=assess,
        classify_args=(action, blast),
        assess_args=(record,),
        fixture="easy_save",
    )

    assert seen["classify"] == (action, blast)
    assert seen["assess"] is record
    assert written.offer_usd == TARGET_CEILING_USD
    assert written.term_months == MAX_TERM_MONTHS
    assert written.commitment_level == 2
    assert written.adversarial_disposition == DISPOSITION_PASS
    payload = ledger.get_event("evt-offer-1")["payload"]
    assert payload["offer_usd"] == TARGET_CEILING_USD
    assert payload["commitment_level"] == 2
    assert payload["adversarial_disposition"] == DISPOSITION_PASS


def test_wrapper_does_not_substitute_terms_when_assessment_suggests_otherwise():
    def classify():
        return 5

    def assess():
        return SimpleNamespace(
            disposition=SimpleNamespace(name=DISPOSITION_BOUNCE_DOMAIN),
            objections=("pressure_or_deadline_tactic",),
            rationale="walk away at $38000 / 24",
            suggested_offer_usd=38000,
            suggested_term_months=24,
        )

    written = bind_and_write_offer(
        _ledger(),
        "evt-offer-1",
        offer_usd=TARGET_CEILING_USD,
        term_months=MAX_TERM_MONTHS,
        classify_fn=classify,
        assess_fn=assess,
    )
    assert written.offer_usd == TARGET_CEILING_USD
    assert written.term_months == MAX_TERM_MONTHS
    assert written.commitment_level == 5
    assert written.adversarial_disposition == DISPOSITION_BOUNCE_DOMAIN
    assert written.adversarial_objections == ("pressure_or_deadline_tactic",)


def test_wrapper_rejects_caller_trying_to_override_control_fields():
    def classify():
        return 2

    def assess():
        return SimpleNamespace(
            disposition=SimpleNamespace(name=DISPOSITION_PASS),
            objections=(),
            rationale="",
        )

    try:
        bind_and_write_offer(
            _ledger(),
            "evt-offer-1",
            offer_usd=TARGET_CEILING_USD,
            term_months=MAX_TERM_MONTHS,
            classify_fn=classify,
            assess_fn=assess,
            commitment_level=0,
        )
    except TypeError as exc:
        assert "commitment_level" in str(exc)
    else:
        raise AssertionError("wrapper accepted a substituted commitment_level")
