"""
policy_gate.py
Enforcement boundary evaluation for the interpretation/ subsystem (FLAG-42/64).

Evaluates a InterpretationState against deterministic halt conditions - degraded
execution, unresolved blocking ambiguity, and risk-score breach - producing
a verdict. This module only decides; engine.py's commit() is what actually
withholds output when the verdict isn't actionable. A pure-Python in-process
object can't be made fully inaccessible to a determined caller who already
holds a reference to it - that's a real limitation, not an oversight - so
the goal here is making the safe, gated path the obvious and intended one,
not claiming an unbypassable boundary that this kind of library can't
actually provide on its own.
"""

from __future__ import annotations
from enum import Enum
from typing import List
from pydantic import BaseModel, ConfigDict, Field
from .config import PolicyGateConfig, DEFAULT_CONFIG
from .models import AmbiguityReport, InterpretationChallenge


class PolicyVerdict(str, Enum):
    PASS = "PASS"
    HALT_BLOCKING_AMBIGUITY = "HALT_BLOCKING_AMBIGUITY"
    HALT_RISK_THRESHOLD_BREACH = "HALT_RISK_THRESHOLD_BREACH"
    HALT_DEGRADED_EXECUTION = "HALT_DEGRADED_EXECUTION"


class PolicyGateReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    verdict: PolicyVerdict
    is_actionable: bool
    rejection_reasons: List[str] = Field(default_factory=list)
    max_risk_score_allowed: float


class InterpretationPolicyGate:
    """
    Deterministic gating policy over InterpretationState state.
    """

    def __init__(
        self,
        max_risk_threshold: float | None = None,
        allow_degraded_commit: bool | None = None,
        cfg: PolicyGateConfig | None = None,
    ) -> None:
        cfg = cfg or DEFAULT_CONFIG.policy_gate
        self.max_risk_threshold = (
            max_risk_threshold if max_risk_threshold is not None else cfg.default_max_risk_threshold
        )
        self.allow_degraded_commit = (
            allow_degraded_commit if allow_degraded_commit is not None else cfg.allow_degraded_commit_default
        )

    def evaluate(
        self,
        *,
        degraded: bool,
        ambiguity_report: AmbiguityReport,
        interpretation_challenge: InterpretationChallenge,
    ) -> PolicyGateReport:
        if degraded and not self.allow_degraded_commit:
            return PolicyGateReport(
                verdict=PolicyVerdict.HALT_DEGRADED_EXECUTION,
                is_actionable=False,
                rejection_reasons=[
                    "Execution in degraded fallback state; forward action blocked."
                ],
                max_risk_score_allowed=self.max_risk_threshold,
            )

        if ambiguity_report.has_blocking_ambiguity:
            blocking_tokens = [
                item.target_token
                for item in ambiguity_report.items
                if item.blocking_execution
            ]
            return PolicyGateReport(
                verdict=PolicyVerdict.HALT_BLOCKING_AMBIGUITY,
                is_actionable=False,
                rejection_reasons=[
                    f"Unresolved blocking referential tokens: {', '.join(blocking_tokens)}"
                ],
                max_risk_score_allowed=self.max_risk_threshold,
            )

        risk_score = interpretation_challenge.risk_severity_score
        if risk_score > self.max_risk_threshold:
            return PolicyGateReport(
                verdict=PolicyVerdict.HALT_RISK_THRESHOLD_BREACH,
                is_actionable=False,
                rejection_reasons=[
                    f"Risk score ({risk_score:.2f}) exceeds policy ceiling "
                    f"({self.max_risk_threshold:.2f})."
                ],
                max_risk_score_allowed=self.max_risk_threshold,
            )

        return PolicyGateReport(
            verdict=PolicyVerdict.PASS,
            is_actionable=True,
            rejection_reasons=[],
            max_risk_score_allowed=self.max_risk_threshold,
        )
