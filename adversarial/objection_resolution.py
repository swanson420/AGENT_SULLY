"""adversarial/objection_resolution.py

Implements decision/triage_gate/README.md's fix #6: "Adversarial
loop-back objection matching (fix #6) — schema, not prose." Confirmed
missing before this file was written: grepped the whole codebase for
Objection, ChallengedField, RequiredChangeType, ResolutionAssertion,
validate_resolution -- zero matches anywhere.

Placement note: the README groups this with fix #5 inside
decision/triage_gate/README.md and doesn't give an explicit path, which
could be read as "put this in decision/triage_gate/". Placed in
adversarial/ instead, next to counterparty_model.py, for the same reason
check_divergence went into decision/contracts/ rather than
decision/triage_gate/: this module needs CounterpartyModel.detect_kind()
to avoid duplicating its detection patterns, and adversarial/ sits above
decision/triage_gate/ in the architecture (workflow-roster.md: the
adversarial check "sits between Triage output and the Action Gate").
Importing adversarial/ from inside decision/triage_gate/ would be the
same upward-dependency violation already fixed once in ledger/ledger.py
and avoided once in blast_radius.py's check_divergence.

The problem this closes, per the README: CounterpartyModel authorizes
exactly one loop-back per decision (adversarial/counterparty_model.py's
own docstring: "a bounded feedback edge"). Before this file existed,
nothing verified that a loop-back's revised text actually addressed the
specific objection that triggered it -- a caller could resubmit an
unchanged record, or change an unrelated field, and the loop-back would
be spent with nothing to show for it. validate_resolution() closes that:
it requires the same objection_id, the same challenged field, and (for
pattern-based objections) that the specific pattern which fired no longer
matches the revised text.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Tuple

from adversarial.counterparty_model import CounterpartyAssessment
from decision.contracts.decision_package import DecisionRecord


class ChallengedField(Enum):
    """Which field of a DecisionRecord's context an objection targets.
    Two members because CounterpartyModel's four objection kinds only
    ever read from two sources (see _source_text() and _objections() in
    counterparty_model.py): raw_payload text for three of them,
    record.rationale for the fourth."""
    RAW_PAYLOAD = auto()
    RATIONALE = auto()


class RequiredChangeType(Enum):
    """What kind of change a ResolutionAssertion must demonstrate to
    satisfy an Objection."""
    PATTERN_REMOVED = auto()  # the specific matched pattern must no longer fire
    VALUE_CHANGED = auto()    # generic: value must differ, no pattern re-check


# Every one of CounterpartyModel's current objection kinds is pattern-
# detected, so all four map to PATTERN_REMOVED today. A future objection
# kind that isn't pattern-based (e.g. one requiring a numeric delta rather
# than a text pattern disappearing) would use VALUE_CHANGED instead --
# the enum exists for that case, not because any current kind needs it.
_KIND_TO_FIELD = {
    "pressure_or_deadline_tactic": ChallengedField.RAW_PAYLOAD,
    "inconsistent_numeric_claims": ChallengedField.RAW_PAYLOAD,
    "counterparty_leverage_or_position_exposure": ChallengedField.RAW_PAYLOAD,
    "counterparty_risk_in_rationale": ChallengedField.RATIONALE,
}


@dataclass(frozen=True)
class Objection:
    """One specific, structured objection -- not a bare string. Built
    from a CounterpartyAssessment's objections by build_objections(),
    not constructed by hand in normal use (objection_id needs to be
    stable and traceable back to the assessment that raised it)."""
    objection_id: str
    objection_kind: str
    challenged_field: ChallengedField
    required_change: RequiredChangeType
    description: str


@dataclass(frozen=True)
class ResolutionAssertion:
    """A caller's claim that a loop-back's revised record resolves a
    specific Objection. old_value/new_value are the challenged field's
    text before and after the revision -- both required, so "restates
    the same value" is checkable directly (old == new) without needing
    to re-fetch the prior record."""
    objection_id: str
    field: ChallengedField
    old_value: str
    new_value: str


@dataclass(frozen=True)
class ResolutionCheckResult:
    satisfied: bool
    rationale: str


def build_objections(
    assessment: CounterpartyAssessment,
    raw_payload_text: str,
    rationale_text: str,
) -> Tuple[Objection, ...]:
    """Convert a CounterpartyAssessment's bare objection-kind strings
    into structured Objection instances. Deterministic IDs (not random)
    so the same assessment always produces the same objection_ids --
    matters because a ResolutionAssertion has to reference one by ID.
    """
    built = []
    for kind in assessment.objections:
        field = _KIND_TO_FIELD.get(kind)
        if field is None:
            raise ValueError(f"Unrecognized objection kind, no field mapping: {kind!r}")
        built.append(
            Objection(
                objection_id=f"obj-{kind}",
                objection_kind=kind,
                challenged_field=field,
                required_change=RequiredChangeType.PATTERN_REMOVED,
                description=f"{kind} detected in "
                f"{'raw_payload' if field is ChallengedField.RAW_PAYLOAD else 'rationale'}.",
            )
        )
    return tuple(built)


def validate_resolution(
    objection: Objection,
    assertion: ResolutionAssertion,
) -> ResolutionCheckResult:
    """Deterministically checks all three things the README requires:
    same objection_id, same field, and the required direction of change.
    A resolution that changes an unrelated field, restates the same
    value, or moves the wrong direction fails match here -- the caller
    is responsible for then treating that identically to a second
    unresolved objection (forced escalation to domain bounce), per the
    README; this function only reports the mismatch, it doesn't route.
    """
    if assertion.objection_id != objection.objection_id:
        return ResolutionCheckResult(
            False,
            f"ResolutionAssertion references objection_id="
            f"{assertion.objection_id!r}, but this is {objection.objection_id!r}.",
        )

    if assertion.field is not objection.challenged_field:
        return ResolutionCheckResult(
            False,
            f"Resolution touched {assertion.field.name}, but the objection "
            f"challenged {objection.challenged_field.name} -- an unrelated "
            f"field was changed instead of the one that was actually challenged.",
        )

    if assertion.new_value == assertion.old_value:
        return ResolutionCheckResult(
            False,
            "Resolution restates the same value -- no actual change was made.",
        )

    if objection.required_change is RequiredChangeType.PATTERN_REMOVED:
        # Reuse CounterpartyModel's own detection logic -- not a second,
        # separately-maintained copy of the pattern that could drift.
        from adversarial.counterparty_model import CounterpartyModel

        still_present = CounterpartyModel.detect_kind(assertion.new_value, objection.objection_kind)
        if still_present:
            return ResolutionCheckResult(
                False,
                f"The specific pattern for {objection.objection_kind!r} still "
                f"matches the revised text -- the objection was not actually resolved.",
            )

    return ResolutionCheckResult(
        True,
        f"Objection {objection.objection_id!r} resolved: {objection.challenged_field.name} "
        f"changed and the triggering pattern no longer matches.",
    )
