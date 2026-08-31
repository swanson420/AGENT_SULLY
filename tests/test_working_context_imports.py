"""Guards EpistemicTag/EpistemicRecord single-definition status.

Mirrors tests/test_interpretation_imports.py, which guards WorkingContext
the same way. interpretation/ owns epistemic-tag semantics (see
decision/contracts/README.md's "Why this folder exists" note: an earlier
EpistemicTag was deliberately deleted rather than migrated into
decision/contracts/, because it isn't a triage-gate data shape).
working_context/epistemic_tags.py re-exports rather than redefines — this
test is what makes that a verified invariant instead of an assumption.
"""

from importlib import import_module

from interpretation.models import EpistemicRecord, EpistemicTag


def test_working_context_reexports_canonical_epistemic_tag():
    module = import_module("working_context.epistemic_tags")
    assert module.EpistemicTag is EpistemicTag
    assert EpistemicTag.__module__ == "interpretation.models"


def test_working_context_reexports_canonical_epistemic_record():
    module = import_module("working_context.epistemic_tags")
    assert module.EpistemicRecord is EpistemicRecord
    assert EpistemicRecord.__module__ == "interpretation.models"


def test_decision_contracts_has_no_parallel_epistemic_tag():
    """Guards against the exact pattern decision/contracts/README.md
    documents as already-retired-once: an EpistemicTag living beside the
    triage gate's own schema instead of in its owning layer."""
    decision_package = import_module("decision.contracts.decision_package")
    assert not hasattr(decision_package, "EpistemicTag")
    assert not hasattr(decision_package, "EpistemicRecord")
