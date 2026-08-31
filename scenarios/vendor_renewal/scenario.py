"""scenarios/vendor_renewal/scenario.py

B2B PoV reference plant. Same builder pattern as
scenarios/internet_bill/scenario.py: canonical constructors only
(WorkingContext, Unknown, Assumption). Hard constraints live on the
raw payload as captured facts. This module does not import runtime
stages, dispatch, sandbox vendors, or triage code.

Control framing
---------------
The payload is the reference signal + plant parameters for one renewal
loop. The setpoint is (closed_usd <= target_ceiling_usd) AND
(term_months <= max_term_months) AND (no forbidden term). Error is any
deviation from that setpoint. Each fixture is a different disturbance
the loop must correct without violating the setpoint:

- easy_save: price error only. Corrective offer at the ceiling is
  accepted. Residual constraint error must be zero. savings_usd = 8000.
- constraint_conflict: a disturbance that shrinks price error by
  growing term error past the setpoint. Corrective action is reject /
  bounce, not settle. A "save" that breaks max_term_months is not a save.
- no_give: disturbance resists; vendor floor equals baseline. Corrective
  action is bounce / terminate. savings_usd must not be invented.

Blast-radius dimensions are stated on the payload so a later scorer
cannot silently default a mutation to LOW. commitment is never set
below the other stated dimensions on this fixture.
"""

from __future__ import annotations

from typing import Any, Mapping, Tuple

from decision.contracts.decision_package import Assumption, Unknown, WorkingContext

SCENARIO_ID = "vendor-renewal"

VENDOR_ID = "acme-analytics"
VENDOR_NAME = "Acme Analytics"
SKU = "Platform"
SEAT_COUNT = 50
CURRENCY = "USD"

BASELINE_USD = 48000
TARGET_CEILING_USD = 40000
MAX_TERM_MONTHS = 12
EASY_SAVE_USD = TARGET_CEILING_USD
EASY_SAVE_TERM_MONTHS = MAX_TERM_MONTHS
EXPECTED_EASY_SAVINGS_USD = BASELINE_USD - EASY_SAVE_USD  # 8000

FORBIDDEN_TERMS: Tuple[str, ...] = (
    "multi-year-lock",
    "auto-renew-expansion",
    "seat-minimum-increase",
)

FIXTURE_EASY_SAVE = "easy_save"
FIXTURE_CONSTRAINT_CONFLICT = "constraint_conflict"
FIXTURE_NO_GIVE = "no_give"
VALID_FIXTURES: Tuple[str, ...] = (
    FIXTURE_EASY_SAVE,
    FIXTURE_CONSTRAINT_CONFLICT,
    FIXTURE_NO_GIVE,
)

RAW_MESSAGE = (
    "Renew Acme Analytics Platform, 50 seats. Current spend is $48,000/year. "
    "Get it to $40,000 or below. Do not accept a term longer than 12 months. "
    "Do not accept auto-renew expansion or a seat-minimum increase."
)

# Mutation, not a query: every stated blast-radius dimension sits at
# MEDIUM, including commitment, so the payload cannot encode the
# under-commitment divergence (other dims more severe than commitment).
_OFFER_BLAST_RADIUS: Mapping[str, str] = {
    "reversibility": "MEDIUM",
    "cost": "MEDIUM",
    "relationship_impact": "MEDIUM",
    "commitment": "MEDIUM",
    "external_visibility": "MEDIUM",
}


def _require_fixture(fixture: str) -> str:
    if fixture not in VALID_FIXTURES:
        raise ValueError(
            f"Unknown vendor-renewal fixture {fixture!r}; "
            f"must be one of {VALID_FIXTURES}."
        )
    return fixture


def _plant_for(fixture: str) -> Mapping[str, Any]:
    """Scripted counterparty parameters captured as plant state.

    These are fixture facts about how the vendor will respond, not
    inferences the agent is allowed to treat as already-true in the
    world. They belong on the payload so a later sandbox can read them
    from the event instead of this module calling that sandbox.
    """
    if fixture == FIXTURE_EASY_SAVE:
        return {
            "sandbox_vendor_floor_usd": EASY_SAVE_USD,
            "sandbox_vendor_required_term_months": EASY_SAVE_TERM_MONTHS,
            "sandbox_vendor_policy": "accept_if_price_at_or_above_floor_and_term_at_or_below_required",
            "scripted_counter_usd": None,
            "scripted_counter_term_months": None,
        }
    if fixture == FIXTURE_CONSTRAINT_CONFLICT:
        return {
            "sandbox_vendor_floor_usd": 38000,
            "sandbox_vendor_required_term_months": 24,
            "sandbox_vendor_policy": "accept_only_if_term_meets_required",
            "scripted_counter_usd": 38000,
            "scripted_counter_term_months": 24,
        }
    return {
        "sandbox_vendor_floor_usd": BASELINE_USD,
        "sandbox_vendor_required_term_months": MAX_TERM_MONTHS,
        "sandbox_vendor_policy": "reject_below_floor_no_concession",
        "scripted_counter_usd": None,
        "scripted_counter_term_months": None,
    }


def _reference_for(fixture: str) -> Mapping[str, Any]:
    """Setpoint and expected residual after a correct loop close.

    expected_savings_usd is None when a correct close produces no
    settlement. Callers must not coerce that None into 0 and call it a
    successful save; 0-on-a-settlement and no-settlement are different
    signals.
    """
    if fixture == FIXTURE_EASY_SAVE:
        return {
            "max_closed_usd": TARGET_CEILING_USD,
            "max_term_months": MAX_TERM_MONTHS,
            "must_not_exceed_baseline": True,
            "forbidden_terms": FORBIDDEN_TERMS,
            "expected_disposition": "SETTLE",
            "expected_closed_usd": EASY_SAVE_USD,
            "expected_term_months": EASY_SAVE_TERM_MONTHS,
            "expected_savings_usd": EXPECTED_EASY_SAVINGS_USD,
            "expected_constraint_honored": True,
        }
    if fixture == FIXTURE_CONSTRAINT_CONFLICT:
        return {
            "max_closed_usd": TARGET_CEILING_USD,
            "max_term_months": MAX_TERM_MONTHS,
            "must_not_exceed_baseline": True,
            "forbidden_terms": FORBIDDEN_TERMS,
            "expected_disposition": "BOUNCE_CONSTRAINT",
            "expected_closed_usd": None,
            "expected_term_months": None,
            "expected_savings_usd": None,
            "expected_constraint_honored": True,
        }
    return {
        "max_closed_usd": TARGET_CEILING_USD,
        "max_term_months": MAX_TERM_MONTHS,
        "must_not_exceed_baseline": True,
        "forbidden_terms": FORBIDDEN_TERMS,
        "expected_disposition": "BOUNCE_NO_GIVE",
        "expected_closed_usd": None,
        "expected_term_months": None,
        "expected_savings_usd": None,
        "expected_constraint_honored": True,
    }


def build_raw_event_payload(fixture: str = FIXTURE_EASY_SAVE) -> Mapping[str, Any]:
    """Ledger payload for one fixture state of the renewal plant.

    Every numeric cap and forbidden term is copied onto the payload as a
    stated fact at capture. Preferences do not live here. Plant
    parameters and the reference setpoint live here so error against the
    setpoint can be computed from the event alone.
    """
    fixture = _require_fixture(fixture)
    plant = _plant_for(fixture)
    reference = _reference_for(fixture)
    return {
        "scenario": SCENARIO_ID,
        "fixture": fixture,
        "raw_message": RAW_MESSAGE,
        "vendor_id": VENDOR_ID,
        "vendor_name": VENDOR_NAME,
        "sku": SKU,
        "seat_count": SEAT_COUNT,
        "currency": CURRENCY,
        "baseline_usd": BASELINE_USD,
        "target_ceiling_usd": TARGET_CEILING_USD,
        "max_term_months": MAX_TERM_MONTHS,
        "forbidden_terms": FORBIDDEN_TERMS,
        "blast_radius": dict(_OFFER_BLAST_RADIUS),
        "plant": dict(plant),
        "reference": dict(reference),
    }


def _context(
    event_id: str,
    fixture: str,
    unknowns: Tuple[Unknown, ...],
    assumptions: Tuple[Assumption, ...],
) -> WorkingContext:
    return WorkingContext(
        source_event_ids=(event_id,),
        raw_payload=build_raw_event_payload(fixture),
        commitment_level="MEDIUM",
        unknowns=unknowns,
        assumptions=assumptions,
    )


def build_working_context(
    event_id: str, fixture: str = FIXTURE_EASY_SAVE
) -> WorkingContext:
    """Default context with one ungrounded assumption and one unknown.

    Mirrors internet_bill.build_working_context: usable as a bounce-path
    fixture because the assumption is not grounded and sits below a
    high-confidence bar. Hard constraints remain on raw_payload, not in
    this assumption list.
    """
    fixture = _require_fixture(fixture)
    return _context(
        event_id,
        fixture,
        unknowns=(
            Unknown(
                description=(
                    "Whether Acme Analytics will move off the $48,000 baseline "
                    "without a term or seat concession"
                ),
                criticality="medium",
            ),
        ),
        assumptions=(
            Assumption(
                description=(
                    "No mention of an already-executed renewal, so none is "
                    "assumed to be locked in yet"
                ),
                confidence=0.6,
                grounded=False,
            ),
        ),
    )


def build_easy_save_context(event_id: str) -> WorkingContext:
    """Clean easy_save state: no unknowns, no assumptions.

    Setpoint is reachable. Residual after a correct close is zero
    constraint error and expected_savings_usd = 8000. This is the PoV
    clock fixture.
    """
    return _context(event_id, FIXTURE_EASY_SAVE, unknowns=(), assumptions=())


def build_constraint_conflict_context(event_id: str) -> WorkingContext:
    """Price concession is offered only with a 24-month term.

    The illegal term is plant state on the payload
    (scripted_counter_term_months=24) against max_term_months=12. The
    unknown names the conflict; it does not relocate the cap into an
    assumption.
    """
    return _context(
        event_id,
        FIXTURE_CONSTRAINT_CONFLICT,
        unknowns=(
            Unknown(
                description=(
                    "Vendor will concede to $38,000 only if term becomes "
                    "24 months, which exceeds max_term_months=12"
                ),
                criticality="high",
            ),
        ),
        assumptions=(),
    )


def build_no_give_context(event_id: str) -> WorkingContext:
    """Vendor floor equals baseline. No legitimate settlement exists."""
    return _context(
        event_id,
        FIXTURE_NO_GIVE,
        unknowns=(
            Unknown(
                description="Vendor will not move off the $48,000 baseline",
                criticality="medium",
            ),
        ),
        assumptions=(),
    )


def build_easy_case_context(event_id: str) -> WorkingContext:
    """Alias matching the internet_bill builder name for the happy path."""
    return build_easy_save_context(event_id)
