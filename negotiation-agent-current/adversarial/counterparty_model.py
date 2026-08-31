"""Adversarial counterparty check used as a pre-action decision gate.

The check is deliberately a bounded feedback edge: at most one loop-back to
triage is authorized for a decision package.  A second objection is never
re-entered into the model; it fails closed to a human/domain bounce.
"""
from dataclasses import dataclass
from enum import Enum, auto
import re
from typing import Tuple

from decision.contracts.decision_package import DecisionRecord, RouteType
from decision.triage_gate.config import DEFAULT_CONFIG, TriageGateConfig


class AdversarialDisposition(Enum):
    PASS = auto()
    LOOP_BACK = auto()
    BOUNCE_DOMAIN = auto()


@dataclass(frozen=True)
class CounterpartyAssessment:
    disposition: AdversarialDisposition
    objections: Tuple[str, ...]
    rationale: str
    next_recursion_depth: int

    @property
    def route(self) -> RouteType:
        if self.disposition is AdversarialDisposition.PASS:
            return RouteType.ACT_SILENTLY
        return RouteType.BOUNCE_DOMAIN


class CounterpartyModel:
    """Evaluate a DecisionRecord for predictable counterparty objections.

    This class does not recursively invoke triage.  It returns one of three
    explicit dispositions so the caller owns the single feedback edge.
    """

    _PRESSURE_PATTERNS = (
        re.compile(r"\b(?:act|answer|respond|decide)\s+(?:now|immediately)\b", re.I),
        re.compile(r"\b(?:last|final)\s+(?:chance|offer|deadline)\b", re.I),
        re.compile(r"\b(?:expires?|deadline|today only)\b", re.I),
    )
    _INCONSISTENT_NUMBER = re.compile(
        r"\$\s*\d+(?:\.\d+)?[^\n]{0,80}\$\s*\d+(?:\.\d+)?", re.I
    )
    _LEVERAGE_PATTERNS = (
        re.compile(r"\b(?:walk[- ]away|bottom line|reservation price)\b", re.I),
        re.compile(r"\b(?:must|have to|required to)\b", re.I),
    )

    def __init__(self, config: TriageGateConfig = DEFAULT_CONFIG) -> None:
        if config.max_recursion_depth < 1:
            raise ValueError("max_recursion_depth must permit the single adversarial loop-back")
        self._config = config

    @classmethod
    def detect_kind(cls, text: str, kind: str) -> bool:
        """Check whether one specific named objection kind's pattern(s)
        match the given text, in isolation from the other three.

        Exists so objection_resolution.py's validate_resolution() can
        re-check whether a *specific* objection was actually addressed
        in a loop-back's revised text, by re-running the exact same
        pattern this class itself uses in _objections() -- not a second,
        separately-maintained copy of the same regex that could drift
        out of sync with this one.
        """
        if kind == "pressure_or_deadline_tactic":
            return any(pattern.search(text) for pattern in cls._PRESSURE_PATTERNS)
        if kind == "inconsistent_numeric_claims":
            return bool(cls._INCONSISTENT_NUMBER.search(text))
        if kind == "counterparty_leverage_or_position_exposure":
            return any(pattern.search(text) for pattern in cls._LEVERAGE_PATTERNS)
        if kind == "counterparty_risk_in_rationale":
            return "counterparty" in text.lower()
        raise ValueError(f"Unrecognized objection kind: {kind!r}")

    def assess(self, record: DecisionRecord, *, recursion_depth: int = 0) -> CounterpartyAssessment:
        """Assess one decision pass without recursively invoking another pass."""
        record.validate()
        if recursion_depth < 0:
            raise ValueError("recursion_depth cannot be negative")

        text = self._source_text(record)
        objections = self._objections(text, record)

        if not objections:
            return CounterpartyAssessment(
                disposition=AdversarialDisposition.PASS,
                objections=(),
                rationale="No material counterparty objection detected.",
                next_recursion_depth=recursion_depth,
            )

        next_depth = recursion_depth + 1
        if next_depth <= self._config.max_recursion_depth:
            return CounterpartyAssessment(
                disposition=AdversarialDisposition.LOOP_BACK,
                objections=tuple(objections),
                rationale=(
                    "Counterparty objection detected; one bounded loop-back to triage is authorized."
                ),
                next_recursion_depth=next_depth,
            )

        return CounterpartyAssessment(
            disposition=AdversarialDisposition.BOUNCE_DOMAIN,
            objections=tuple(objections),
            rationale=(
                "Counterparty objection remains unresolved after the maximum adversarial loop-back; "
                "human/domain clarification is required."
            ),
            next_recursion_depth=recursion_depth,
        )

    @staticmethod
    def _source_text(record: DecisionRecord) -> str:
        payload = record.context.raw_payload
        if not isinstance(payload, dict):
            return str(payload)
        parts = [str(value) for value in payload.values() if isinstance(value, (str, int, float))]
        return " ".join(parts)

    def _objections(self, text: str, record: DecisionRecord) -> list[str]:
        objections: list[str] = []
        if any(pattern.search(text) for pattern in self._PRESSURE_PATTERNS):
            objections.append("pressure_or_deadline_tactic")
        if self._INCONSISTENT_NUMBER.search(text):
            objections.append("inconsistent_numeric_claims")
        if any(pattern.search(text) for pattern in self._LEVERAGE_PATTERNS):
            objections.append("counterparty_leverage_or_position_exposure")
        if record.rationale and "counterparty" in record.rationale.lower():
            objections.append("counterparty_risk_in_rationale")
        return list(dict.fromkeys(objections))
