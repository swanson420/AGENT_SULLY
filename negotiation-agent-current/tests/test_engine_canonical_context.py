from unittest.mock import MagicMock

from decision.contracts.decision_package import WorkingContext
from interpretation.engine import InterpretationPipelineEngine
from interpretation.models import (
    AmbiguityReport,
    ExtractedContext,
    IntentDecoupling,
    InterpretationChallenge,
    PremiseRegistry,
)


def test_engine_returns_canonical_context_and_preserves_upstream_provenance():
    extracted = ExtractedContext(objectives=["reduce the bill"])
    premises = PremiseRegistry()
    intent = IntentDecoupling(
        core_goal="reduce the bill",
        proposed_method="negotiate",
        method_is_constraint=False,
        coupling_strength=0.2,
        alternative_vectors_permissible=True,
    )
    ambiguity = AmbiguityReport()
    challenge = InterpretationChallenge(
        competing_interpretation="none",
        failure_scenario="none",
        risk_severity_score=0.0,
    )

    interrogator = MagicMock()
    interrogator.extract_context.return_value = extracted
    premise_extractor = MagicMock()
    premise_extractor.extract_premises.return_value = premises
    goal_vs_method = MagicMock()
    goal_vs_method.decouple_intent.return_value = intent
    ambiguity_detector = MagicMock()
    ambiguity_detector.detect_ambiguity.return_value = ambiguity
    challenger = MagicMock()
    challenger.challenge.return_value = challenge

    engine = InterpretationPipelineEngine(
        interrogator,
        premise_extractor,
        goal_vs_method,
        ambiguity_detector,
        challenger,
    )

    upstream = WorkingContext(
        source_event_ids=("evt-verified-001",),
        raw_payload={"raw_input": "reduce the bill", "scenario": "internet-bill"},
        commitment_level="LOW",
    )

    result, report = engine.execute("reduce the bill", "ledger-history", upstream)

    assert type(result) is WorkingContext
    assert result.source_event_ids == upstream.source_event_ids
    assert result.raw_payload == upstream.raw_payload
    assert report.is_actionable is True
    assert not hasattr(result, "extracted_context")
