"""Dispatch gate: commitment ≥ 3 requires a granted human_ack on the ledger."""

from __future__ import annotations

from typing import Any, Optional

from action.human_ack import ledger_has_granted_ack

ACK_THRESHOLD = 3


class DispatchBlocked(ValueError):
    """Offer may not be written. Baseline is left as-is."""

    def __init__(self, commitment_level: int) -> None:
        self.commitment_level = commitment_level
        super().__init__(
            f"dispatch blocked: commitment_level={commitment_level} requires human_ack"
        )


def assert_dispatch_allowed(
    commitment_level: int,
    ledger: Any,
    baseline_event_id: Optional[str] = None,
) -> None:
    """baseline_event_id scopes the ack check to this specific negotiation.
    Without it, any granted ack anywhere on the ledger — even one written
    for a different, unrelated negotiation — would satisfy this gate.
    Optional only so existing direct callers don't break; close_path.py
    always passes it."""
    if not isinstance(commitment_level, int) or isinstance(commitment_level, bool):
        raise DispatchBlocked(commitment_level if isinstance(commitment_level, int) else -1)
    if commitment_level < ACK_THRESHOLD:
        return
    if ledger_has_granted_ack(ledger, baseline_event_id):
        return
    raise DispatchBlocked(commitment_level)
