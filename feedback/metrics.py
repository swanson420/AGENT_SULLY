"""Ledger read model  observe only.

Aggregates savings and outcome counts from persisted event payloads.
Each call rescan the ledger. Nothing is cached. Policy is not updated.

A settlement payload is counted only if it re-validates through
evaluate_settlement and its stored savings_usd matches the recomputed
value. A halt payload is counted only if it re-validates through
evaluate_halt against the allowlisted reason and detail codes. A
payload that claims either type and fails that check is an invalid
observation, not an outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence

from action.halt import (
    ALLOWED_DETAIL_CODES,
    ALLOWED_HALT_REASONS,
    HaltRecord,
    HaltRefused,
    REASON_CONSTRAINT,
    evaluate_halt,
)
from action.settlement import SettlementRefused, evaluate_settlement


class ReadableLedger(Protocol):
    @property
    def entries(self) -> Sequence[Mapping[str, Any]]: ...


@dataclass(frozen=True)
class MetricsSnapshot:
    baseline_count: int
    settlement_count: int
    invalid_settlement_count: int
    halt_count: int
    invalid_halt_count: int
    halt_by_reason: Mapping[str, int]
    constraint_by_detail: Mapping[str, int]
    total_savings_usd: int


def _payload_of(entry: Mapping[str, Any]) -> Mapping[str, Any] | None:
    payload = entry.get("payload")
    if isinstance(payload, Mapping):
        return payload
    return None


def _validated_savings(payload: Mapping[str, Any]) -> int | None:
    """Return recomputed savings if the payload is a real settlement."""
    if payload.get("event_type") != "settlement":
        return None
    if payload.get("constraint_honored") is not True:
        return None
    try:
        record = evaluate_settlement(
            baseline_usd=payload.get("baseline_usd"),
            closed_usd=payload.get("closed_usd"),
            max_term_months=payload.get("max_term_months"),
            term_months=payload.get("term_months"),
            target_ceiling_usd=payload.get("target_ceiling_usd"),
            forbidden_terms=payload.get("forbidden_terms") or (),
            accepted_terms=payload.get("accepted_terms") or (),
        )
    except (SettlementRefused, TypeError, ValueError):
        return None
    stored = payload.get("savings_usd")
    if stored != record.savings_usd:
        return None
    return record.savings_usd


def _validated_halt_record(payload: Mapping[str, Any]) -> HaltRecord | None:
    """Revalidated halt record, or None if the payload is not a real halt."""
    if payload.get("event_type") != "halt":
        return None
    try:
        record = evaluate_halt(
            reason=payload.get("reason"),
            detail_codes=payload.get("detail_codes") or (),
            human_required=payload.get("human_required"),
            evidence_event_ids=payload.get("evidence_event_ids") or (),
            vendor_id=payload.get("vendor_id"),
            fixture=payload.get("fixture"),
        )
    except (HaltRefused, TypeError, ValueError):
        return None
    if payload.get("reason") != record.reason:
        return None
    if payload.get("human_required") is not record.human_required:
        return None
    stored_details = tuple(payload.get("detail_codes") or ())
    if stored_details != record.detail_codes:
        return None
    if record.reason not in ALLOWED_HALT_REASONS:
        return None
    if any(code not in ALLOWED_DETAIL_CODES for code in record.detail_codes):
        return None
    return record


def collect(ledger: ReadableLedger) -> MetricsSnapshot:
    """Scan ledger.entries once. No stored running totals."""
    if not hasattr(ledger, "entries"):
        raise TypeError("ledger must expose an entries snapshot")

    baseline_count = 0
    settlement_count = 0
    invalid_settlement_count = 0
    halt_count = 0
    invalid_halt_count = 0
    halt_by_reason = {reason: 0 for reason in sorted(ALLOWED_HALT_REASONS)}
    constraint_by_detail = {code: 0 for code in sorted(ALLOWED_DETAIL_CODES)}
    total_savings_usd = 0

    for entry in ledger.entries:
        if not isinstance(entry, Mapping):
            continue
        payload = _payload_of(entry)
        if payload is None:
            continue
        event_type = payload.get("event_type")
        if event_type == "baseline":
            baseline_count += 1
            continue
        if event_type == "settlement":
            savings = _validated_savings(payload)
            if savings is None:
                invalid_settlement_count += 1
                continue
            settlement_count += 1
            total_savings_usd += savings
            continue
        if event_type == "halt":
            record = _validated_halt_record(payload)
            if record is None:
                invalid_halt_count += 1
                continue
            halt_count += 1
            halt_by_reason[record.reason] += 1
            if record.reason == REASON_CONSTRAINT:
                for code in record.detail_codes:
                    constraint_by_detail[code] += 1
            continue

    return MetricsSnapshot(
        baseline_count=baseline_count,
        settlement_count=settlement_count,
        invalid_settlement_count=invalid_settlement_count,
        halt_count=halt_count,
        invalid_halt_count=invalid_halt_count,
        halt_by_reason=MappingProxyType(dict(halt_by_reason)),
        constraint_by_detail=MappingProxyType(dict(constraint_by_detail)),
        total_savings_usd=total_savings_usd,
    )


def total_savings_usd(ledger: ReadableLedger) -> int:
    return collect(ledger).total_savings_usd


def settlement_count(ledger: ReadableLedger) -> int:
    return collect(ledger).settlement_count


def baseline_count(ledger: ReadableLedger) -> int:
    return collect(ledger).baseline_count


def halt_count(ledger: ReadableLedger) -> int:
    return collect(ledger).halt_count


def halt_by_reason(ledger: ReadableLedger) -> Mapping[str, int]:
    return collect(ledger).halt_by_reason


def constraint_by_detail(ledger: ReadableLedger) -> Mapping[str, int]:
    return collect(ledger).constraint_by_detail
