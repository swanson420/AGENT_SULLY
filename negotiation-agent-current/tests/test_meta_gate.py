from decision.contracts.decision_package import ActionType
from decision.triage_gate.conservative_defaults import (
    FallbackState,
    conservative_default_for,
)
from reasoning.control_panel.meta_gate import MetaGate, UncertaintyKind


def test_meta_uncertainty_uses_deterministic_nonimplicit_fallback():
    first = MetaGate.resolve_uncertainty(ActionType.EXECUTE_QUERY, UncertaintyKind.META)
    second = MetaGate.resolve_uncertainty(ActionType.EXECUTE_QUERY, UncertaintyKind.META)
    assert first == second
    assert first.interrupted is False
    assert first.fallback.state is FallbackState.HOLD_POSITION


def test_meta_uncertainty_escalates_actions_unsafe_to_silence():
    result = MetaGate.resolve_uncertainty(ActionType.MUTATE_STATE, UncertaintyKind.META)
    assert result.interrupted is True
    assert result.fallback.silence_is_unsafe is True
    assert result.fallback.state is FallbackState.FORCED_ESCALATION


def test_domain_uncertainty_is_an_interruption():
    result = MetaGate.resolve_uncertainty(ActionType.QUERY_INFO, UncertaintyKind.DOMAIN)
    assert result.interrupted is True


def test_classification_prefers_domain_over_meta():
    assert MetaGate.classify(domain_uncertain=True, meta_uncertain=True) is UncertaintyKind.DOMAIN
    assert MetaGate.classify(meta_uncertain=True) is UncertaintyKind.META
    assert MetaGate.classify() is None


def test_every_action_has_an_explicit_default():
    for action in ActionType:
        default = conservative_default_for(action)
        assert default.rationale
        assert default.state in set(FallbackState)
