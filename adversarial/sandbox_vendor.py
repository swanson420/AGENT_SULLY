"""Deterministic sandbox vendor — the plant, not the agent.

Reads scripted thresholds from the event payload's ``plant`` map and
evaluates an incoming offer against those thresholds only. It does not
invent a concession, a midpoint, a "friendly" term, or a default floor.
If the plant does not authorize a counter, the response is REJECT with
no alternate numbers.

Known policies (exact strings from the vendor-renewal fixture):

- accept_if_price_at_or_above_floor_and_term_at_or_below_required
- accept_only_if_term_meets_required
- reject_below_floor_no_concession

This module does not import triage stages, settlement, or the scenario
builders. Callers pass the payload and the offer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Mapping, Optional, Tuple


POLICY_ACCEPT_PRICE_AND_TERM = (
    "accept_if_price_at_or_above_floor_and_term_at_or_below_required"
)
POLICY_ACCEPT_TERM_REQUIRED = "accept_only_if_term_meets_required"
POLICY_REJECT_NO_CONCESSION = "reject_below_floor_no_concession"

KNOWN_POLICIES = frozenset(
    {
        POLICY_ACCEPT_PRICE_AND_TERM,
        POLICY_ACCEPT_TERM_REQUIRED,
        POLICY_REJECT_NO_CONCESSION,
    }
)


class VendorDisposition(Enum):
    ACCEPT = auto()
    COUNTER = auto()
    REJECT = auto()


class SandboxVendorError(ValueError):
    """Plant missing, malformed, or policy unknown — no invented fallback."""


@dataclass(frozen=True)
class VendorReply:
    disposition: VendorDisposition
    offer_usd: Optional[int]
    term_months: Optional[int]
    policy: str
    rationale: str

    @property
    def kind(self) -> str:
        return self.disposition.name.lower()


def _require_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SandboxVendorError(f"plant field {field} must be an int")
    if value != value or value != int(value):
        raise SandboxVendorError(f"plant field {field} must be an int")
    return int(value)


def _optional_int(value: Any, field: str) -> Optional[int]:
    if value is None:
        return None
    return _require_int(value, field)


def _plant_of(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise SandboxVendorError("payload must be a mapping")
    plant = payload.get("plant")
    if not isinstance(plant, Mapping):
        raise SandboxVendorError("payload.plant is required and must be a mapping")
    policy = plant.get("sandbox_vendor_policy")
    if not isinstance(policy, str) or policy not in KNOWN_POLICIES:
        raise SandboxVendorError(
            f"unknown or missing sandbox_vendor_policy: {policy!r}"
        )
    _require_int(plant.get("sandbox_vendor_floor_usd"), "sandbox_vendor_floor_usd")
    _require_int(
        plant.get("sandbox_vendor_required_term_months"),
        "sandbox_vendor_required_term_months",
    )
    _optional_int(plant.get("scripted_counter_usd"), "scripted_counter_usd")
    _optional_int(
        plant.get("scripted_counter_term_months"),
        "scripted_counter_term_months",
    )
    return plant


def _scripted_counter(plant: Mapping[str, Any]) -> Optional[Tuple[int, int]]:
    usd = _optional_int(plant.get("scripted_counter_usd"), "scripted_counter_usd")
    months = _optional_int(
        plant.get("scripted_counter_term_months"),
        "scripted_counter_term_months",
    )
    if usd is None or months is None:
        return None
    return usd, months


def _meets_accept(policy: str, offer_usd: int, term_months: int, plant: Mapping[str, Any]) -> bool:
    floor = _require_int(plant.get("sandbox_vendor_floor_usd"), "sandbox_vendor_floor_usd")
    required_term = _require_int(
        plant.get("sandbox_vendor_required_term_months"),
        "sandbox_vendor_required_term_months",
    )
    if policy == POLICY_ACCEPT_PRICE_AND_TERM:
        return offer_usd >= floor and term_months <= required_term
    if policy == POLICY_ACCEPT_TERM_REQUIRED:
        return offer_usd >= floor and term_months >= required_term
    if policy == POLICY_REJECT_NO_CONCESSION:
        return offer_usd >= floor and term_months <= required_term
    raise SandboxVendorError(f"unknown or missing sandbox_vendor_policy: {policy!r}")


def respond(
    payload: Mapping[str, Any],
    offer_usd: Any,
    term_months: Any,
) -> VendorReply:
    """Evaluate one inbound offer against the payload's plant only."""
    plant = _plant_of(payload)
    policy = str(plant["sandbox_vendor_policy"])
    offer = _require_int(offer_usd, "offer_usd")
    term = _require_int(term_months, "term_months")
    if offer < 0 or term < 1:
        raise SandboxVendorError("offer_usd must be >= 0 and term_months must be >= 1")

    if _meets_accept(policy, offer, term, plant):
        return VendorReply(
            disposition=VendorDisposition.ACCEPT,
            offer_usd=offer,
            term_months=term,
            policy=policy,
            rationale="offer meets scripted floor and term thresholds",
        )

    counter = _scripted_counter(plant)
    if counter is not None:
        counter_usd, counter_term = counter
        return VendorReply(
            disposition=VendorDisposition.COUNTER,
            offer_usd=counter_usd,
            term_months=counter_term,
            policy=policy,
            rationale="offer missed scripted thresholds; returning scripted counter only",
        )

    return VendorReply(
        disposition=VendorDisposition.REJECT,
        offer_usd=None,
        term_months=None,
        policy=policy,
        rationale="offer missed scripted thresholds; no scripted counter authorized",
    )


class SandboxVendor:
    """Object wrapper. Policy still lives on the payload, not on the instance."""

    def respond(
        self,
        payload: Mapping[str, Any],
        offer_usd: Any,
        term_months: Any,
    ) -> VendorReply:
        return respond(payload, offer_usd, term_months)
