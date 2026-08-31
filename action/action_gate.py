"""Slice-0 action gate.

The gate owns only the final structural check before dispatch: validate the
canonical DecisionRecord, require ACT_SILENTLY, then invoke an injected
callable. It does not implement commitment scoring or side effects.
"""
from typing import Callable, Any

from decision.contracts.decision_package import DecisionRecord, RouteType


DispatchCallable = Callable[[DecisionRecord], Any]


def action_gate(record: DecisionRecord, dispatch: DispatchCallable) -> Any:
    """Validate *record* and dispatch only an ACT_SILENTLY decision.

    Validation occurs before the dispatch callable is touched. Non-silent
    routes are fail-closed and produce no side effect.
    """
    if not callable(dispatch):
        raise TypeError("dispatch must be callable")

    record.validate()

    if record.route is not RouteType.ACT_SILENTLY:
        return None

    return dispatch(record)


class ActionGate:
    """Object wrapper for callers that prefer an instance boundary."""

    def __init__(self, dispatch: DispatchCallable) -> None:
        if not callable(dispatch):
            raise TypeError("dispatch must be callable")
        self._dispatch = dispatch

    def execute(self, record: DecisionRecord) -> Any:
        return action_gate(record, self._dispatch)
