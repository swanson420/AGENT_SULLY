from importlib import import_module

from decision.contracts.decision_package import WorkingContext as CanonicalWorkingContext


def test_interpretation_engine_imports_as_package():
    module = import_module("interpretation.engine")
    assert module.InterpretationPipelineEngine is not None


def test_interpretation_engine_uses_canonical_working_context_contract():
    module = import_module("interpretation.engine")
    assert module.CanonicalWorkingContext is CanonicalWorkingContext
    assert CanonicalWorkingContext.__module__ == "decision.contracts.decision_package"
    assert not hasattr(import_module("interpretation.models"), "WorkingContext")
