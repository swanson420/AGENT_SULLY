"""Leaf config for commitment and adversarial modules.

Not the triage pipeline. Frozen defaults only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Tuple

from decision.contracts.decision_package import ActionType


def _default_escalation() -> FrozenSet[ActionType]:
    return frozenset(
        {
            ActionType.MUTATE_STATE,
            ActionType.TERMINATE_SYSTEM,
            ActionType.OVERRIDE_SECURITY,
            ActionType.DEPLOY_PAYLOAD,
            ActionType.PURGE_RECORDS,
        }
    )


def _default_gates() -> Tuple[str, ...]:
    return (
        "interpretation_stable",
        "context_anchored",
        "ledger_anchored",
        "blast_radius_calibrated",
        "assumptions_grounded",
    )


@dataclass(frozen=True)
class TriageGateConfig:
    mandatory_escalation_actions: FrozenSet[ActionType] = field(
        default_factory=_default_escalation
    )
    max_recursion_depth: int = 1
    required_pre_action_gates: Tuple[str, ...] = field(default_factory=_default_gates)


DEFAULT_CONFIG = TriageGateConfig()
