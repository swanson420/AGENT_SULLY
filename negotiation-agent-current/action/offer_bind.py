"""Bind external commitment and adversarial signals onto write_offer.

Computes the two control readings, then forwards the caller's terms
unchanged. This wrapper does not clamp dollars, rewrite term, or replace
a computed level with a default.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Optional

from action.offer import OfferRecord, write_offer


ClassifyFn = Callable[..., int]
AssessFn = Callable[..., Any]


def bind_and_write_offer(
    ledger: Any,
    event_id: str,
    *,
    offer_usd: Any,
    term_months: Any,
    classify_fn: ClassifyFn,
    assess_fn: AssessFn,
    classify_args: tuple[Any, ...] = (),
    classify_kwargs: Optional[Mapping[str, Any]] = None,
    assess_args: tuple[Any, ...] = (),
    assess_kwargs: Optional[Mapping[str, Any]] = None,
    **offer_kwargs: Any,
) -> OfferRecord:
    """Evaluate signals, write offer with original terms.

    ``offer_usd`` and ``term_months`` are passed to the writer as given.
    Commitment and adversarial fields come only from ``classify_fn`` and
    ``assess_fn``. Extra ``offer_kwargs`` must not include those four
    control fields or the terms.
    """
    reserved = {
        "offer_usd",
        "term_months",
        "commitment_level",
        "adversarial_disposition",
        "adversarial_objections",
        "adversarial_rationale",
    }
    clash = reserved.intersection(offer_kwargs)
    if clash:
        raise TypeError(f"wrapper does not accept substituted fields: {sorted(clash)}")

    level = classify_fn(*classify_args, **dict(classify_kwargs or {}))
    assessment = assess_fn(*assess_args, **dict(assess_kwargs or {}))

    disposition = assessment.disposition.name
    objections = tuple(assessment.objections)
    rationale = assessment.rationale

    return write_offer(
        ledger,
        event_id,
        offer_usd=offer_usd,
        term_months=term_months,
        commitment_level=level,
        adversarial_disposition=disposition,
        adversarial_objections=objections,
        adversarial_rationale=rationale,
        **offer_kwargs,
    )
