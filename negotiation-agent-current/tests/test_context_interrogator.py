from interpretation.context_interrogator import ContextInterrogator
from interpretation.models import ExtractedContext


def test_context_interrogator_satisfies_output_interface():
    result = ContextInterrogator().extract_context(
        "I want the bill reduced. We must keep the 12-month cap.",
        "prior event",
    )
    assert isinstance(result, ExtractedContext)
    assert result.objectives
    assert result.requirements
    assert result.facts


def test_context_interrogator_bounds_combined_input():
    result = ContextInterrogator(max_input_chars=10).extract_context("1234567890", "abcdef")
    assert result.is_truncated is True
    assert len("".join(result.facts)) <= 10


def test_context_interrogator_clause_boundaries_do_not_swallow_following_clause():
    result = ContextInterrogator().extract_context(
        "We must preserve the cap, but we can change the provider.", ""
    )
    assert result.requirements == ["preserve the cap"]
