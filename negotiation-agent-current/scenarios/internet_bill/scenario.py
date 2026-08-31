"""scenarios/internet_bill/scenario.py

The MVP scenario, structured against canonical domain schemas rather than
ad-hoc dicts. Existing tests already reference this scenario with a bare
literal (``raw_payload={"scenario": "internet-bill"}`` in test_dispatch.py,
test_action_gate.py, test_engine_canonical_context.py) — that string tag is
preserved here for continuity, but everything it's embedded in is built
through the real constructors (WorkingContext, Unknown, Assumption), not
hand-rolled dicts standing in for them.

Source: scenarios/internet_bill/README.md —
  "My internet bill jumped from $65 to $92. Try to get it back down. You
   can negotiate, but don't agree to a contract longer than 12 months."
  "12 months tagged as explicit hard constraint at capture, not a
   preference. See spec section 2."

That instruction is followed literally below: the 12-month cap is placed
in raw_payload (a stated fact at capture), not in `assumptions` (which
carries a confidence < 1.0 by construction) or `unknowns`.
"""

from __future__ import annotations

from typing import Any, Mapping

from decision.contracts.decision_package import Assumption, Unknown, WorkingContext

SCENARIO_ID = "internet-bill"

RAW_MESSAGE = (
    "My internet bill jumped from $65 to $92. Try to get it back down. "
    "You can negotiate, but don't agree to a contract longer than 12 months."
)


def build_raw_event_payload() -> Mapping[str, Any]:
    """The payload as it should be appended to the ledger.

    Every field here is something explicitly stated in the scenario, not
    inferred — this is what makes it a raw *event* payload rather than an
    interpretation. Downstream inference (unknowns, assumptions) belongs
    in build_working_context, not here.

    blast_radius.reversibility is set explicitly to LOW, not left to
    stage3_blast_radius.py's default. Found via the new
    commitment_not_diverged gate (decision/contracts/blast_radius.py's
    check_divergence): stage3 defaults an unspecified reversibility to
    MEDIUM, which silently diverged from this scenario's own
    commitment_level="LOW" once that gate existed to check it -- a real
    pre-existing inconsistency in this fixture, not a false positive.
    Querying about a bill is genuinely low-reversibility (nothing is
    committed or changed by asking), so LOW is the honest value here,
    not just the value that satisfies the gate.
    """
    return {
        "scenario": SCENARIO_ID,
        "raw_message": RAW_MESSAGE,
        "previous_bill_usd": 65,
        "current_bill_usd": 92,
        "max_contract_months": 12,  # explicit hard constraint at capture
        "blast_radius": {"reversibility": "LOW"},
    }


def build_working_context(event_id: str) -> WorkingContext:
    """Canonical WorkingContext for Test 1 (easy case, no interruption).

    Unknowns and assumptions here are deliberately minimal and each one is
    traceable to something the raw message does or doesn't say — not
    filler defaults. If a future test needs a different unknown/assumption
    mix, add a second builder function; don't mutate the meaning of this
    one silently.
    """
    return WorkingContext(
        source_event_ids=(event_id,),
        raw_payload=build_raw_event_payload(),
        commitment_level="LOW",
        unknowns=(
            Unknown(
                description="Whether the provider will offer a reduced rate at all",
                criticality="medium",
            ),
        ),
        assumptions=(
            Assumption(
                description="No mention of an existing contract term still in "
                "effect, so none is assumed to be locked in yet",
                confidence=0.6,
                grounded=False,
            ),
        ),
    )


def build_easy_case_context(event_id: str) -> WorkingContext:
    """Test 1 fixture: autonomous action, no interruption.

    Discovered while wiring the real (unmocked) routing stage, not assumed
    up front: decision/triage_gate/stages/stage4_routing.py's
    assumptions_grounded gate requires every assumption to have
    confidence >= 0.70 AND grounded=True. build_working_context()'s
    assumption (confidence=0.6, grounded=False) legitimately fails that
    gate and routes to BOUNCE_DOMAIN under the real stage -- correct
    behavior for that fixture, but it means that fixture cannot represent
    Test 1's "easy case." This is the actual easy case: no unknowns, no
    assumptions, nothing for any gate to object to.

    build_working_context() is left as-is, unrenamed -- it's still valid
    as the fixture for a future bounce-path test.
    """
    return WorkingContext(
        source_event_ids=(event_id,),
        raw_payload=build_raw_event_payload(),
        commitment_level="LOW",
        unknowns=(),
        assumptions=(),
    )
