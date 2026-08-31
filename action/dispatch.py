"""Audited action dispatch boundary.

The dispatcher validates the canonical decision, commits its audit record to
an injected ledger before delivery, and only then invokes the target
interface.  It deliberately contains no transport-specific side effects.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol

from decision.contracts.decision_package import DecisionRecord, RouteType


class AuditLedger(Protocol):
    def record_decision_view(self, record: DecisionRecord) -> bool: ...


TargetCallable = Callable[[DecisionRecord], Any]


def dispatch(
    record: DecisionRecord,
    ledger: AuditLedger,
    target: TargetCallable | None = None,
) -> Any:
    """Audit *record* successfully before invoking its target.

    No target delivery occurs unless the canonical decision validates and the
    ledger accepts the immutable audit record.  Slice-0 has no real transport,
    so an omitted target returns ``"success"`` after the audit commit.
    """
    if not hasattr(ledger, "record_decision_view") or not callable(ledger.record_decision_view):
        raise TypeError("ledger must provide a callable record_decision_view")
    if target is not None and not callable(target):
        raise TypeError("target must be callable when supplied")

    record.validate()
    if record.route is not RouteType.ACT_SILENTLY:
        raise ValueError("dispatch requires ACT_SILENTLY route")

    if not ledger.record_decision_view(record):
        raise RuntimeError("audit commitment failed; target delivery blocked")

    if target is None:
        return "success"
    return target(record)


class ActionDispatcher:
    """Reusable audited dispatch object."""

    def __init__(self, ledger: AuditLedger, target: TargetCallable | None = None) -> None:
        self._ledger = ledger
        self._target = target

    def execute(self, record: DecisionRecord) -> Any:
        return dispatch(record, self._ledger, self._target)
