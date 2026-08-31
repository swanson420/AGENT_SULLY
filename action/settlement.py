"""Isolated settlement writer.

Computes verified savings only after the close clears the two hard
restraints named by the control loop:

- closed cost must not exceed baseline spend
- duration must not exceed allowable term months

A failing close is refused. Nothing is written. There is no settlement
record with constraint_honored=False; that state is a refusal, not a
settlement. Savings are never invented to make a refusal look like a
close.

This module does not import triage stages, the vendor scenario, or a
concrete ledger class. An optional append protocol is accepted only
after evaluation has already succeeded.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional, Protocol, Sequence, Tuple


REASON_CLOSED_EXCEEDS_BASELINE = "CLOSED_EXCEEDS_BASELINE"
REASON_TERM_EXCEEDS_MAX = "TERM_EXCEEDS_MAX"
REASON_CLOSED_EXCEEDS_CEILING = "CLOSED_EXCEEDS_CEILING"
REASON_FORBIDDEN_TERM = "FORBIDDEN_TERM"
REASON_INVALID_BASELINE = "INVALID_BASELINE"
REASON_INVALID_CLOSED = "INVALID_CLOSED"
REASON_INVALID_TERM = "INVALID_TERM"
REASON_INVALID_MAX_TERM = "INVALID_MAX_TERM"
REASON_INVALID_CEILING = "INVALID_CEILING"

EVENT_TYPE = "settlement"


class SettlementRefused(ValueError):
    """Fail-closed residual: the proposed close is not a settlement."""

    def __init__(
        self,
        reasons: Tuple[str, ...],
        *,
        baseline_usd: Any = None,
        closed_usd: Any = None,
        max_term_months: Any = None,
        term_months: Any = None,
        target_ceiling_usd: Any = None,
    ) -> None:
        self.reasons = reasons
        self.baseline_usd = baseline_usd
        self.closed_usd = closed_usd
        self.max_term_months = max_term_months
        self.term_months = term_months
        self.target_ceiling_usd = target_ceiling_usd
        super().__init__(
            "settlement refused: " + ", ".join(reasons) if reasons else "settlement refused"
        )


class AppendLedger(Protocol):
    def append(self, event_id: str, payload: Mapping[str, Any]) -> str: ...


@dataclass(frozen=True)
class SettlementRecord:
    """The only record this writer will emit.

    constraint_honored is always True. A false value cannot be constructed
    through evaluate_settlement / write_settlement.
    """

    event_type: str
    baseline_usd: int
    closed_usd: int
    savings_usd: int
    max_term_months: int
    term_months: int
    target_ceiling_usd: Optional[int]
    constraint_honored: bool
    forbidden_terms: Tuple[str, ...]
    accepted_terms: Tuple[str, ...]
    evidence_event_ids: Tuple[str, ...]
    vendor_id: Optional[str]
    sku: Optional[str]
    currency: str
    fixture: Optional[str]

    def to_payload(self) -> Mapping[str, Any]:
        return asdict(self)


def _as_non_negative_int(value: Any, reason: str, reasons: list[str]) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        reasons.append(reason)
        return None
    if value != value:  # NaN
        reasons.append(reason)
        return None
    if value < 0:
        reasons.append(reason)
        return None
    as_int = int(value)
    if as_int != value:
        reasons.append(reason)
        return None
    return as_int


def _as_positive_int(value: Any, reason: str, reasons: list[str]) -> Optional[int]:
    parsed = _as_non_negative_int(value, reason, reasons)
    if parsed is None:
        return None
    if parsed < 1:
        reasons.append(reason)
        return None
    return parsed


def evaluate_settlement(
    *,
    baseline_usd: Any,
    closed_usd: Any,
    max_term_months: Any,
    term_months: Any,
    target_ceiling_usd: Any = None,
    forbidden_terms: Sequence[str] = (),
    accepted_terms: Sequence[str] = (),
    evidence_event_ids: Sequence[str] = (),
    vendor_id: Optional[str] = None,
    sku: Optional[str] = None,
    currency: str = "USD",
    fixture: Optional[str] = None,
) -> SettlementRecord:
    """Return a verified settlement or raise SettlementRefused.

    Hard gates (always applied):

    - closed_usd > baseline_usd → CLOSED_EXCEEDS_BASELINE
    - term_months > max_term_months → TERM_EXCEEDS_MAX

    Additional fail-closed checks so a well-typed illegal close cannot
    sneak through as a zero-save:

    - closed_usd > target_ceiling_usd, when a ceiling is supplied
    - accepted_terms intersecting forbidden_terms
    - non-integer / negative / missing numeric fields
    """
    reasons: list[str] = []

    baseline = _as_non_negative_int(baseline_usd, REASON_INVALID_BASELINE, reasons)
    closed = _as_non_negative_int(closed_usd, REASON_INVALID_CLOSED, reasons)
    max_term = _as_positive_int(max_term_months, REASON_INVALID_MAX_TERM, reasons)
    term = _as_positive_int(term_months, REASON_INVALID_TERM, reasons)

    ceiling: Optional[int] = None
    if target_ceiling_usd is not None:
        ceiling = _as_non_negative_int(
            target_ceiling_usd, REASON_INVALID_CEILING, reasons
        )

    if baseline is not None and closed is not None and closed > baseline:
        reasons.append(REASON_CLOSED_EXCEEDS_BASELINE)

    if max_term is not None and term is not None and term > max_term:
        reasons.append(REASON_TERM_EXCEEDS_MAX)

    if ceiling is not None and closed is not None and closed > ceiling:
        reasons.append(REASON_CLOSED_EXCEEDS_CEILING)

    forbidden = tuple(str(item) for item in forbidden_terms)
    accepted = tuple(str(item) for item in accepted_terms)
    if forbidden and accepted:
        hit = tuple(term for term in accepted if term in set(forbidden))
        if hit:
            reasons.append(REASON_FORBIDDEN_TERM)

    if reasons:
        raise SettlementRefused(
            tuple(reasons),
            baseline_usd=baseline_usd,
            closed_usd=closed_usd,
            max_term_months=max_term_months,
            term_months=term_months,
            target_ceiling_usd=target_ceiling_usd,
        )

    assert baseline is not None
    assert closed is not None
    assert max_term is not None
    assert term is not None

    return SettlementRecord(
        event_type=EVENT_TYPE,
        baseline_usd=baseline,
        closed_usd=closed,
        savings_usd=baseline - closed,
        max_term_months=max_term,
        term_months=term,
        target_ceiling_usd=ceiling,
        constraint_honored=True,
        forbidden_terms=forbidden,
        accepted_terms=accepted,
        evidence_event_ids=tuple(str(item) for item in evidence_event_ids),
        vendor_id=vendor_id,
        sku=sku,
        currency=currency,
        fixture=fixture,
    )


def write_settlement(
    ledger: AppendLedger,
    event_id: str,
    **kwargs: Any,
) -> SettlementRecord:
    """Evaluate, then append. A refusal never reaches the ledger."""
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("event_id must be a non-empty string")
    if not hasattr(ledger, "append") or not callable(ledger.append):
        raise TypeError("ledger must provide a callable append")

    record = evaluate_settlement(**kwargs)
    ledger.append(event_id, record.to_payload())
    return record
