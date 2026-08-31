"""
engine.py
Deterministic pipeline orchestrator for the interpretation/ subsystem.

Attests each stage call itself, from the real input/output it directly
observes immediately after the call returns - never from a claim the stage
supplies (FLAG-63). Stage protocols in base.py and the five stage
implementations are unchanged; nothing about their interface needed to
change for this to be genuine (FLAG-62 avoided by design, not patched
around).

execute() returns the full pipeline state plus a PolicyGateReport, for
introspection/observability - this subsystem is a recommendation layer,
not the final authority (per its own scope). commit() is the intended
production entrypoint and always honors the gate's verdict (FLAG-64): it
never returns a partial or unrestricted record list when the verdict isn't
actionable. execute_and_serialize() is kept for backward compatibility but
is explicitly documented as bypassing the gate - nothing is silently
removed or silently made unsafe without saying so.
"""

from __future__ import annotations
import logging
from typing import List, Tuple
from .base import (
    AmbiguityDetectorStage,
    ContextInterrogatorStage,
    GoalVsMethodStage,
    InterpretationChallengeStage,
    PremiseExtractorStage,
)
from .models import (
    AmbiguityReport,
    EpistemicRecord,
    ExtractedContext,
    IntentDecoupling,
    InterpretationChallenge,
    PremiseRegistry,
    StageAttestation,
)
from .policy_gate import InterpretationPolicyGate, PolicyGateReport
from .serializer import WorkingContextSerializer
from decision.contracts.decision_package import (
    Assumption,
    Unknown,
    WorkingContext as CanonicalWorkingContext,
)

logger = logging.getLogger(__name__)


class InterpretationPipelineEngine:
    """
    Executes the pre-decision interpretation pipeline against incoming user input and ledger history.
    """

    def __init__(
        self,
        interrogator: ContextInterrogatorStage,
        premise_extractor: PremiseExtractorStage,
        goal_vs_method: GoalVsMethodStage,
        ambiguity_detector: AmbiguityDetectorStage,
        challenger: InterpretationChallengeStage,
        policy_gate: InterpretationPolicyGate | None = None,
        serializer: WorkingContextSerializer | None = None,
    ) -> None:
        self.interrogator = interrogator
        self.premise_extractor = premise_extractor
        self.goal_vs_method = goal_vs_method
        self.ambiguity_detector = ambiguity_detector
        self.challenger = challenger
        self.policy_gate = policy_gate or InterpretationPolicyGate()
        self.serializer = serializer or WorkingContextSerializer()

    def execute(
        self,
        raw_input: str,
        ledger: str,
        upstream_context: CanonicalWorkingContext,
    ) -> Tuple[CanonicalWorkingContext, PolicyGateReport]:
        """
        Executes the interpretation pipeline in strict topological order,
        attesting each stage from the real input/output this method itself
        directly observes.
        """
        attestations: List[StageAttestation] = []
        degraded = False
        try:
            # Stage 1: Literal context & premise extraction
            extracted_context = self.interrogator.extract_context(raw_input, ledger)
            attestations.append(
                StageAttestation.generate(
                    "context_interrogator",
                    raw_input + "|" + ledger,
                    extracted_context,
                )
            )

            premise_registry = self.premise_extractor.extract_premises(
                raw_input, extracted_context
            )
            attestations.append(
                StageAttestation.generate(
                    "premise_extractor",
                    raw_input + "|" + extracted_context.model_dump_json(),
                    premise_registry,
                )
            )

            # Stage 2: Intent decoupling & ambiguity quantification
            intent = self.goal_vs_method.decouple_intent(
                extracted_context, premise_registry
            )
            attestations.append(
                StageAttestation.generate(
                    "goal_vs_method",
                    extracted_context.model_dump_json()
                    + "|"
                    + premise_registry.model_dump_json(),
                    intent,
                )
            )

            ambiguity = self.ambiguity_detector.detect_ambiguity(
                extracted_context, premise_registry
            )
            attestations.append(
                StageAttestation.generate(
                    "ambiguity_detector",
                    extracted_context.model_dump_json()
                    + "|"
                    + premise_registry.model_dump_json(),
                    ambiguity,
                )
            )

            # Stage 3: Adversarial validation & challenge
            challenge = self.challenger.challenge(
                extracted_context, intent, premise_registry, ambiguity
            )
            attestations.append(
                StageAttestation.generate(
                    "interpretation_challenge",
                    extracted_context.model_dump_json()
                    + "|"
                    + intent.model_dump_json()
                    + "|"
                    + premise_registry.model_dump_json()
                    + "|"
                    + ambiguity.model_dump_json(),
                    challenge,
                )
            )

            working_context = self._to_canonical_context(
                upstream_context, raw_input, extracted_context, premise_registry, ambiguity
            )

        except Exception as err:
            logger.error(
                "Interpretation pipeline failure occurred. Diagnostic code: PIPELINE_STAGE_FAULT[%s]",
                type(err).__name__,
            )
            degraded = True
            ambiguity = AmbiguityReport(has_blocking_ambiguity=True)
            challenge = InterpretationChallenge(
                competing_interpretation="PIPELINE_EXECUTION_FAILURE",
                failure_scenario="Pipeline crashed during parsing; downstream execution halted.",
                risk_severity_score=1.0,
            )
            working_context = self._build_degraded_fallback(upstream_context, raw_input, ledger)

        gate_report = self.policy_gate.evaluate(
            degraded=degraded,
            ambiguity_report=ambiguity,
            interpretation_challenge=challenge,
        )
        return working_context, gate_report

    def commit(
        self,
        raw_input: str,
        ledger: str,
        upstream_context: CanonicalWorkingContext,
    ) -> Tuple[List[EpistemicRecord], PolicyGateReport]:
        """
        The intended production entrypoint. Always honors the policy gate -
        returns an empty record list, never a partial or unrestricted one,
        whenever the gate's verdict is not actionable.
        """
        working_context, gate_report = self.execute(raw_input, ledger, upstream_context)
        if not gate_report.is_actionable:
            logger.warning(
                "Pipeline commit blocked by policy gate. Verdict: %s",
                gate_report.verdict.value,
            )
            return [], gate_report

        return self.serializer.serialize(working_context), gate_report

    def execute_and_serialize(
        self,
        raw_input: str,
        ledger: str,
        upstream_context: CanonicalWorkingContext,
    ) -> List[EpistemicRecord]:
        """
        Kept for backward compatibility. Unlike commit(), this does NOT
        consult the policy gate - it always serializes and returns records
        regardless of degraded/blocking/risk-threshold state. Prefer
        commit() for any production use where the gate's verdict matters.
        """
        working_context, _gate_report = self.execute(raw_input, ledger, upstream_context)
        return self.serializer.serialize(working_context)


    @staticmethod
    def _require_upstream_context(raw_input: str, ledger: str) -> CanonicalWorkingContext:
        """Reject execution without an upstream canonical provenance carrier.

        This compatibility hook is intentionally strict: callers must provide a
        verified canonical context at the execution boundary. The engine never
        manufactures or accepts source event identifiers itself.
        """
        raise RuntimeError(
            "InterpretationPipelineEngine.commit()/execute_and_serialize() require "
            "a canonical upstream context; use execute(..., upstream_context=...) "
            "at the orchestration boundary."
        )

    @staticmethod
    def _to_canonical_context(
        upstream_context: CanonicalWorkingContext,
        raw_input: str,
        extracted_context: ExtractedContext,
        premise_registry: PremiseRegistry,
        ambiguity: AmbiguityReport,
    ) -> CanonicalWorkingContext:
        """Map verified upstream provenance and interpretation results into the canonical contract."""
        unknowns = tuple(
            Unknown(
                description=item.target_token,
                criticality=item.severity.value,
            )
            for item in ambiguity.items
            if item.blocking_execution
        )
        assumptions = tuple(
            Assumption(
                description=p.statement,
                confidence=p.confidence,
                grounded=not p.requires_verification,
            )
            for p in premise_registry.premises
        )
        return CanonicalWorkingContext(
            source_event_ids=tuple(upstream_context.source_event_ids),
            raw_payload=dict(upstream_context.raw_payload) if upstream_context.raw_payload else {"raw_input": raw_input},
            commitment_level=upstream_context.commitment_level,
            unknowns=unknowns,
            assumptions=assumptions,
        )

    def _build_degraded_fallback(self, upstream_context: CanonicalWorkingContext, raw_input: str, ledger: str) -> CanonicalWorkingContext:
        """
        Constructs a safe fail-open WorkingContext upon unhandled exceptions.
        """
        return CanonicalWorkingContext(
            source_event_ids=tuple(upstream_context.source_event_ids),
            raw_payload=dict(upstream_context.raw_payload) if upstream_context.raw_payload else {"raw_input": raw_input},
            commitment_level=upstream_context.commitment_level,
            unknowns=(Unknown(description="PIPELINE_EXECUTION_FAILURE", criticality="HIGH"),),
            assumptions=(),
        )
