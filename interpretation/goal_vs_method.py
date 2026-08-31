"""Stage 2a: separate a user's objective from the proposed execution method."""
from __future__ import annotations

import re
from typing import Iterable

from .config import DEFAULT_CONFIG
from .dlp import redact
from .models import ExtractedContext, IntentDecoupling, PremiseRegistry


class GoalVsMethod:
    """Deterministically decouple goals from proposed methods while locking hard constraints."""

    _LEAD_METHOD = re.compile(
        r"\b(?:by|using|via|through|with)\s+(?P<method>.+?)\s*$", re.IGNORECASE
    )
    _METHOD_CLAUSE = re.compile(
        r"\s*(?:by|using|via|through|with)\s+(?P<method>[^,.;!?]+)", re.IGNORECASE
    )
    _GOAL_LEAD = re.compile(
        r"^(?:to|so that|in order to)\s+", re.IGNORECASE
    )

    # These markers mean the proposed vector is itself part of the user's
    # execution boundary. They are deliberately checked against the complete
    # objective before any clause split so a marker cannot hide in a method tail.
    _HARD_METHOD_MARKERS = re.compile(
        r"\b(?:must|need(?:s)? to|required to|only|cannot|can't|must not|mustn't|without|never|do not|don't|forbid(?:den)?|prohibit(?:ed)?)\b",
        re.IGNORECASE,
    )
    _BOUNDARY_VIOLATION_VERBS = re.compile(
        r"\b(?:bypass\w*|circumvent\w*|override\w*|disable\w*|evade\w*|skip\w*|ignore\w*|suppress\w*)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        high_coupling_ceiling: float | None = None,
        baseline_coupling: float | None = None,
        dependency_coupling_boost: float | None = None,
        premise_confidence_penalty_threshold: float | None = None,
        premise_confidence_penalty_amount: float | None = None,
    ) -> None:
        cfg = DEFAULT_CONFIG.decoupler
        self.high_coupling_ceiling = high_coupling_ceiling if high_coupling_ceiling is not None else cfg.high_coupling_ceiling
        self.baseline_coupling = baseline_coupling if baseline_coupling is not None else cfg.baseline_coupling
        self.dependency_coupling_boost = dependency_coupling_boost if dependency_coupling_boost is not None else cfg.dependency_coupling_boost
        self.premise_confidence_penalty_threshold = premise_confidence_penalty_threshold if premise_confidence_penalty_threshold is not None else cfg.premise_confidence_penalty_threshold
        self.premise_confidence_penalty_amount = premise_confidence_penalty_amount if premise_confidence_penalty_amount is not None else cfg.premise_confidence_penalty_amount

    def decouple_intent(
        self, context: ExtractedContext, premises: PremiseRegistry
    ) -> IntentDecoupling:
        objective = self._select_objective(context.objectives, context.requirements)
        objective = objective.strip()
        method = self._extract_method(objective)
        core_goal = self._core_goal(objective, method)

        # Explicit constraints are authoritative. If the extracted method is
        # represented there, it is not a preference merely because it follows
        # a "by/using/via" construction.
        hard_boundary = bool(
            self._HARD_METHOD_MARKERS.search(objective)
            or self._BOUNDARY_VIOLATION_VERBS.search(objective)
            or self._method_matches_constraint(method, context.constraints)
        )

        low_confidence_premise = any(
            p.confidence < self.premise_confidence_penalty_threshold
            for p in premises.premises
        )
        dependency_present = bool(context.dependencies)

        coupling = self.baseline_coupling
        if dependency_present:
            coupling += self.dependency_coupling_boost
        if low_confidence_premise:
            coupling -= self.premise_confidence_penalty_amount
        coupling = max(0.0, min(self.high_coupling_ceiling, coupling))
        if hard_boundary:
            coupling = self.high_coupling_ceiling

        return IntentDecoupling(
            core_goal=redact(core_goal),
            proposed_method=redact(method),
            method_is_constraint=hard_boundary,
            coupling_strength=coupling,
            alternative_vectors_permissible=not hard_boundary,
        )

    @staticmethod
    def _select_objective(objectives: Iterable[str], requirements: Iterable[str]) -> str:
        for value in objectives:
            if value and value.strip():
                return value.strip()
        for value in requirements:
            if value and value.strip():
                return value.strip()
        return "UNRESOLVED_OBJECTIVE"

    @classmethod
    def _extract_method(cls, objective: str) -> str:
        match = cls._LEAD_METHOD.search(objective)
        if match:
            return match.group("method").strip(" \t,;:")
        match = cls._METHOD_CLAUSE.search(objective)
        if match:
            return match.group("method").strip(" \t,;:")
        return "UNSPECIFIED_METHOD"

    @classmethod
    def _core_goal(cls, objective: str, method: str) -> str:
        if method != "UNSPECIFIED_METHOD":
            # Remove only the method introducer and method clause; do not
            # reinterpret other hard constraint text as a preference.
            pattern = re.compile(
                r"\s*(?:by|using|via|through|with)\s+" + re.escape(method) + r"\s*$",
                re.IGNORECASE,
            )
            goal = pattern.sub("", objective).strip(" \t,;:")
        else:
            goal = objective
        return cls._GOAL_LEAD.sub("", goal).strip(" \t,;:") or "UNRESOLVED_OBJECTIVE"

    @staticmethod
    def _method_matches_constraint(method: str, constraints: Iterable[str]) -> bool:
        if method == "UNSPECIFIED_METHOD":
            return False
        method_tokens = set(re.findall(r"\b[\w'-]+\b", method.lower()))
        if not method_tokens:
            return False
        for constraint in constraints:
            constraint_tokens = set(re.findall(r"\b[\w'-]+\b", constraint.lower()))
            if method.lower() in constraint.lower() or method_tokens.issubset(constraint_tokens):
                return True
        return False
