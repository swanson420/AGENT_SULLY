"""action/commitment_gradient.py

0-5 commitment-level classification, per action/README.md: "Levels 0-5
(informational -> material/irreversible). Higher level -> stronger gating,
independent of what blast-radius alone concluded."

This is deliberately a different axis from WorkingContext.commitment_level
(the LOW/MEDIUM/HIGH/CRITICAL string that feeds into BlastRadiusScore's
"commitment" dimension in stage3_blast_radius.py). That field measures one
dimension of a single action's blast radius. This module measures the
action's overall gradient across all five dimensions plus its category --
the thing action_gate is meant to gate on independently of blast radius
alone, per the README.

Every boundary below traces to a threshold that already exists in
decision/contracts/ or decision/triage_gate/config.py -- nothing here is
an invented cut point:

  Level 5 (irreversible, always escalated) -- ActionType membership in
    TriageGateConfig.mandatory_escalation_actions (already the contract's
    own definition of "this action type is never allowed to resolve
    silently, regardless of anything else" -- stage4_routing.py already
    fails these closed to BOUNCE_META_ESCALATED for exactly this reason).

  Levels 1-4 (material, scaled) -- BlastRadiusScore.to_ordinal_map()'s
    own LOW=1/MEDIUM=2/HIGH=3/CRITICAL=4 weights (decision/contracts/
    blast_radius.py), taking the single worst (max) dimension. A CRITICAL
    dimension already fails stage4's blast_radius_calibrated gate outright
    (has_critical_blast), so ordinal 4 and mandatory-escalation converge on
    the same outcome by two independent routes -- consistent, not
    coincidental.

  Level 0 (informational) -- ActionType.QUERY_INFO specifically, the one
    action type the enum defines as read-only, with every blast-radius
    dimension at LOW (ordinal 1, the floor of to_ordinal_map()). Anything
    else, even QUERY_INFO with an elevated dimension, is not purely
    informational and is scored on the 1-4 scale instead.

No record, context, or score is mutated anywhere in this module -- every
input (BlastRadiusScore, ActionType, TriageGateConfig) is a frozen
dataclass already, and classify_commitment_level returns a new int, it
never calls dataclasses.replace or writes to any field.
"""

from __future__ import annotations

from decision.contracts.blast_radius import BlastRadiusScore
from decision.contracts.decision_package import ActionType
from decision.triage_gate.config import DEFAULT_CONFIG, TriageGateConfig

MAX_COMMITMENT_LEVEL = 5
INFORMATIONAL_LEVEL = 0


def classify_commitment_level(
    action: ActionType,
    blast_radius: BlastRadiusScore,
    config: TriageGateConfig = DEFAULT_CONFIG,
) -> int:
    """Derive the 0-5 commitment gradient for one action + blast radius.

    Pure function: reads action, blast_radius, and config; mutates none
    of them; returns a plain int with no side effects.
    """
    blast_radius.validate()

    if action in config.mandatory_escalation_actions:
        return MAX_COMMITMENT_LEVEL

    ordinal_map = blast_radius.to_ordinal_map()
    max_ordinal = max(ordinal_map.values())  # 1 (LOW) .. 4 (CRITICAL)

    if action is ActionType.QUERY_INFO and max_ordinal == 1:
        return INFORMATIONAL_LEVEL

    # max_ordinal already lands in [1, 4], which is exactly the [1, 4]
    # band of the 0-5 gradient -- no rescaling needed, the two scales
    # were built to line up.
    return max_ordinal
