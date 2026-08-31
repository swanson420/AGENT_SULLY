from interpretation.goal_vs_method import GoalVsMethod
from interpretation.models import ExtractedContext, PremiseRegistry


def test_flexible_method_allows_alternatives():
    ctx = ExtractedContext(objectives=["Reduce the bill by calling the provider"])
    out = GoalVsMethod().decouple_intent(ctx, PremiseRegistry())
    assert out.core_goal == "Reduce the bill"
    assert out.proposed_method == "calling the provider"
    assert out.method_is_constraint is False
    assert out.alternative_vectors_permissible is True


def test_explicit_only_constraint_locks_method():
    ctx = ExtractedContext(objectives=["Reduce the bill only by calling the provider"])
    out = GoalVsMethod().decouple_intent(ctx, PremiseRegistry())
    assert out.method_is_constraint is True
    assert out.alternative_vectors_permissible is False
    assert out.coupling_strength == 0.85


def test_constraint_field_locks_matching_method():
    ctx = ExtractedContext(
        objectives=["Reduce the bill by calling the provider"],
        constraints=["calling the provider is required"],
    )
    out = GoalVsMethod().decouple_intent(ctx, PremiseRegistry())
    assert out.method_is_constraint is True
    assert out.alternative_vectors_permissible is False


def test_boundary_violation_marker_is_not_treated_as_preference():
    ctx = ExtractedContext(objectives=["Reduce the bill by bypassing the approval gate"])
    out = GoalVsMethod().decouple_intent(ctx, PremiseRegistry())
    assert out.method_is_constraint is True
    assert out.alternative_vectors_permissible is False


def test_low_confidence_premise_penalizes_non_locked_coupling():
    from interpretation.models import ExtractedPremise
    ctx = ExtractedContext(objectives=["Reduce the bill by calling the provider"])
    premises = PremiseRegistry(premises=[ExtractedPremise(statement="x", confidence=0.5)])
    out = GoalVsMethod().decouple_intent(ctx, premises)
    assert out.coupling_strength == 0.35
