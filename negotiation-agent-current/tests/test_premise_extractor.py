from interpretation.context_interrogator import ContextInterrogator
from interpretation.premise_extractor import PremiseExtractor


def test_confidence_is_deterministic_by_premise_class():
    raw = (
        "Since we already received clearance, use the API because the service changed. "
        "The account depends on billing."
    )
    ctx = ContextInterrogator().extract_context(raw, "")
    a = PremiseExtractor().extract_premises(raw, ctx)
    b = PremiseExtractor().extract_premises(raw, ctx)
    assert a == b
    scores = [p.confidence for p in a.premises]
    assert 0.50 in scores
    assert 0.80 in scores
    assert 0.75 in scores
    assert 0.85 in scores
    assert 0.90 in scores


def test_low_confidence_presupposition_requires_verification():
    raw = "Since we already received clearance, proceed with the change."
    ctx = ContextInterrogator().extract_context(raw, "")
    premises = PremiseExtractor().extract_premises(raw, ctx)
    assert premises.premises
    p = premises.premises[0]
    assert p.confidence == 0.50
    assert p.requires_verification is True


def test_premise_provenance_offsets_are_source_offsets():
    raw = "Given that the approved cap is fixed, use the API."
    ctx = ContextInterrogator().extract_context(raw, "")
    p = PremiseExtractor().extract_premises(raw, ctx).premises[0]
    assert raw[p.provenance.start_char:p.provenance.end_char] == p.provenance.verbatim_text
