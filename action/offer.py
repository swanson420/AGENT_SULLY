"""Offer writer — persist proposed terms plus evaluated control signals.

Records commitment level and an adversarial assessment digest. It does
not classify commitment or run CounterpartyModel itself. Those stay
outside so this unit does not import triage. It refuses malformed terms
and unverified signals. Nothing is appended on refusal.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Optional, Sequence, Tuple

from action.settlement import AppendLedger

EVENT_TYPE = "offer"

MIN_COMMITMENT_LEVEL = 0
MAX_COMMITMENT_LEVEL = 5

DISPOSITION_PASS = "PASS"
DISPOSITION_LOOP_BACK = "LOOP_BACK"
DISPOSITION_BOUNCE_DOMAIN = "BOUNCE_DOMAIN"

ALLOWED_ADVERSARIAL_DISPOSITIONS = frozenset(
    {
        DISPOSITION_PASS,
        DISPOSITION_LOOP_BACK,
        DISPOSITION_BOUNCE_DOMAIN,
    }
)

SCOPE_SYNTHETIC_OFFER_TEXT = "synthetic_offer_text"
SCOPE_COUNTERPARTY_SOURCE_TEXT = "counterparty_source_text"
ALLOWED_ADVERSARIAL_SCOPES = frozenset(
    {
        SCOPE_SYNTHETIC_OFFER_TEXT,
        SCOPE_COUNTERPARTY_SOURCE_TEXT,
    }
)


class OfferRefused(ValueError):
    """Malformed terms or unverified control signals — do not persist."""

    def __init__(self, reasons: Tuple[str, ...]) -> None:
        self.reasons = reasons
        super().__init__("offer refused: " + ", ".join(reasons) if reasons else "offer refused")


REASON_INVALID_OFFER_USD = "INVALID_OFFER_USD"
REASON_INVALID_TERM = "INVALID_TERM"
REASON_INVALID_COMMITMENT_LEVEL = "INVALID_COMMITMENT_LEVEL"
REASON_INVALID_ADVERSARIAL_DISPOSITION = "INVALID_ADVERSARIAL_DISPOSITION"
REASON_INVALID_ADVERSARIAL_OBJECTIONS = "INVALID_ADVERSARIAL_OBJECTIONS"
REASON_DIGEST_MISMATCH = "DIGEST_MISMATCH"
REASON_INVALID_ADVERSARIAL_SCOPE = "INVALID_ADVERSARIAL_SCOPE"


def adversarial_digest(
    disposition: str,
    objections: Sequence[str],
    rationale: str = "",
) -> str:
    material = json.dumps(
        {
            "disposition": disposition,
            "objections": list(objections),
            "rationale": rationale,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return sha256(material.encode("utf-8")).hexdigest()


def _as_positive_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 1:
        return None
    return value


@dataclass(frozen=True)
class OfferRecord:
    event_type: str
    offer_usd: int
    term_months: int
    commitment_level: int
    adversarial_disposition: str
    adversarial_objections: Tuple[str, ...]
    adversarial_digest: str
    adversarial_check_scope: str
    evidence_event_ids: Tuple[str, ...]
    vendor_id: Optional[str]
    sku: Optional[str]
    currency: str
    fixture: Optional[str]

    def to_payload(self) -> Mapping[str, Any]:
        return asdict(self)


def evaluate_offer(
    *,
    offer_usd: Any,
    term_months: Any,
    commitment_level: Any,
    adversarial_disposition: Any,
    adversarial_objections: Sequence[str] = (),
    adversarial_rationale: str = "",
    expected_digest: Optional[str] = None,  # verify-only; never stored
    adversarial_check_scope: Any = SCOPE_SYNTHETIC_OFFER_TEXT,
    evidence_event_ids: Sequence[str] = (),
    vendor_id: Optional[str] = None,
    sku: Optional[str] = None,
    currency: str = "USD",
    fixture: Optional[str] = None,
) -> OfferRecord:
    reasons: list[str] = []

    parsed_offer = _as_positive_int(offer_usd)
    if parsed_offer is None:
        reasons.append(REASON_INVALID_OFFER_USD)

    parsed_term = _as_positive_int(term_months)
    if parsed_term is None:
        reasons.append(REASON_INVALID_TERM)

    if (
        isinstance(commitment_level, bool)
        or not isinstance(commitment_level, int)
        or commitment_level < MIN_COMMITMENT_LEVEL
        or commitment_level > MAX_COMMITMENT_LEVEL
    ):
        reasons.append(REASON_INVALID_COMMITMENT_LEVEL)
        parsed_level = None
    else:
        parsed_level = commitment_level

    if adversarial_disposition not in ALLOWED_ADVERSARIAL_DISPOSITIONS:
        reasons.append(REASON_INVALID_ADVERSARIAL_DISPOSITION)
        disposition = None
    else:
        disposition = adversarial_disposition

    try:
        objections = tuple(str(item) for item in adversarial_objections)
    except TypeError:
        reasons.append(REASON_INVALID_ADVERSARIAL_OBJECTIONS)
        objections = ()

    if not isinstance(adversarial_rationale, str):
        reasons.append(REASON_INVALID_ADVERSARIAL_OBJECTIONS)
        rationale = ""
    else:
        rationale = adversarial_rationale

    digest = None
    if disposition is not None:
        digest = adversarial_digest(disposition, objections, rationale)
        if expected_digest is not None and expected_digest != digest:
            reasons.append(REASON_DIGEST_MISMATCH)

    if adversarial_check_scope not in ALLOWED_ADVERSARIAL_SCOPES:
        reasons.append(REASON_INVALID_ADVERSARIAL_SCOPE)
        scope = None
    else:
        scope = adversarial_check_scope

    if reasons:
        raise OfferRefused(tuple(reasons))

    assert parsed_offer is not None
    assert parsed_term is not None
    assert parsed_level is not None
    assert disposition is not None
    assert digest is not None
    assert scope is not None

    return OfferRecord(
        event_type=EVENT_TYPE,
        offer_usd=parsed_offer,
        term_months=parsed_term,
        commitment_level=parsed_level,
        adversarial_disposition=disposition,
        adversarial_objections=objections,
        adversarial_digest=digest,
        adversarial_check_scope=scope,
        evidence_event_ids=tuple(str(item) for item in evidence_event_ids),
        vendor_id=vendor_id,
        sku=sku,
        currency=currency or "USD",
        fixture=fixture,
    )


def write_offer(
    ledger: AppendLedger,
    event_id: str,
    **kwargs: Any,
) -> OfferRecord:
    """Evaluate, then append. A refusal never reaches the ledger."""
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("event_id must be a non-empty string")
    if not hasattr(ledger, "append") or not callable(ledger.append):
        raise TypeError("ledger must provide a callable append")
    record = evaluate_offer(**kwargs)
    ledger.append(event_id, record.to_payload())
    return record
