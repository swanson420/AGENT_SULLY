"""Halt writer — persist a verified stop, leave baseline alone.

A halt is an observation that the loop terminated without settlement.
It appends one event. It does not edit, replace, or rewrite any prior
entry. Unknown reason codes are refused and nothing is written.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple

from action.settlement import (
    AppendLedger,
    REASON_CLOSED_EXCEEDS_BASELINE,
    REASON_CLOSED_EXCEEDS_CEILING,
    REASON_FORBIDDEN_TERM,
    REASON_INVALID_BASELINE,
    REASON_INVALID_CEILING,
    REASON_INVALID_CLOSED,
    REASON_INVALID_MAX_TERM,
    REASON_INVALID_TERM,
    REASON_TERM_EXCEEDS_MAX,
)

EVENT_TYPE = "halt"

REASON_VENDOR_REJECT = "VENDOR_REJECT"
REASON_VENDOR_COUNTER = "VENDOR_COUNTER"
REASON_CONSTRAINT = "CONSTRAINT"

ALLOWED_HALT_REASONS = frozenset(
    {
        REASON_VENDOR_REJECT,
        REASON_VENDOR_COUNTER,
        REASON_CONSTRAINT,
    }
)

ALLOWED_DETAIL_CODES = frozenset(
    {
        REASON_CLOSED_EXCEEDS_BASELINE,
        REASON_TERM_EXCEEDS_MAX,
        REASON_CLOSED_EXCEEDS_CEILING,
        REASON_FORBIDDEN_TERM,
        REASON_INVALID_BASELINE,
        REASON_INVALID_CLOSED,
        REASON_INVALID_TERM,
        REASON_INVALID_MAX_TERM,
        REASON_INVALID_CEILING,
    }
)


class HaltRefused(ValueError):
    """Unknown or unverified halt signal — do not persist."""


@dataclass(frozen=True)
class HaltRecord:
    event_type: str
    reason: str
    detail_codes: Tuple[str, ...]
    human_required: bool
    evidence_event_ids: Tuple[str, ...]
    vendor_id: Optional[str]
    fixture: Optional[str]

    def to_payload(self) -> Mapping[str, Any]:
        return asdict(self)


def evaluate_halt(
    *,
    reason: Any,
    detail_codes: Sequence[str] = (),
    human_required: Any = True,
    evidence_event_ids: Sequence[str] = (),
    vendor_id: Optional[str] = None,
    fixture: Optional[str] = None,
) -> HaltRecord:
    if reason not in ALLOWED_HALT_REASONS:
        raise HaltRefused(f"unverified halt reason: {reason!r}")
    if not isinstance(human_required, bool):
        raise HaltRefused("human_required must be a bool")
    details = tuple(str(code) for code in detail_codes)
    unknown = tuple(code for code in details if code not in ALLOWED_DETAIL_CODES)
    if unknown:
        raise HaltRefused(f"unverified halt detail codes: {unknown}")
    if reason == REASON_CONSTRAINT and not details:
        raise HaltRefused("CONSTRAINT halt requires verified detail codes")
    if reason != REASON_CONSTRAINT and details:
        raise HaltRefused("non-constraint halt cannot carry constraint detail codes")
    return HaltRecord(
        event_type=EVENT_TYPE,
        reason=reason,
        detail_codes=details,
        human_required=human_required,
        evidence_event_ids=tuple(str(item) for item in evidence_event_ids),
        vendor_id=vendor_id,
        fixture=fixture,
    )


def write_halt(
    ledger: AppendLedger,
    event_id: str,
    **kwargs: Any,
) -> HaltRecord:
    """Evaluate, then append. A refusal never reaches the ledger."""
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("event_id must be a non-empty string")
    if not hasattr(ledger, "append") or not callable(ledger.append):
        raise TypeError("ledger must provide a callable append")
    record = evaluate_halt(**kwargs)
    ledger.append(event_id, record.to_payload())
    return record
