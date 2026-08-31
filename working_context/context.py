"""working-context/context.py

Mutable current-belief store, per working-context/README.md.

This module holds and revises the *current* WorkingContext — it is
deliberately not a second definition of what a WorkingContext is. Per the
architecture's Layer 0 contract, that type is defined exactly once, in
``decision.contracts.decision_package.WorkingContext``. interpretation/
already enforces this same discipline (see interpretation/serializer.py's
docstring and tests/test_interpretation_imports.py, which asserts
interpretation.models has no WorkingContext attribute of its own).

WorkingContextStore's job is narrower: hold the current instance, allow it
to be revised as new ledger events arrive, and never let a caller mistake
the store for the ledger itself — a store value can be revised; a ledger
entry cannot.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from decision.contracts.decision_package import WorkingContext


class WorkingContextStore:
    """Holds the current WorkingContext and its revision history.

    Not a source of truth: every value here is derived from the ledger.
    If it disagrees with what the ledger says happened, the ledger wins.
    """

    def __init__(self, initial: Optional[WorkingContext] = None) -> None:
        self._current: Optional[WorkingContext] = initial
        self._history: List[WorkingContext] = [initial] if initial is not None else []

    def get(self) -> Optional[WorkingContext]:
        """Return the current WorkingContext, or None if nothing has been set."""
        return self._current

    def set(self, context: WorkingContext) -> None:
        """Revise the current WorkingContext.

        Does not mutate the previous value (WorkingContext is frozen) —
        this replaces the pointer and appends to history, it does not
        edit anything in place.
        """
        if not isinstance(context, WorkingContext):
            raise TypeError(
                f"WorkingContextStore only holds the canonical WorkingContext, "
                f"got {type(context).__name__}"
            )
        self._current = context
        self._history.append(context)

    @property
    def history(self) -> Tuple[WorkingContext, ...]:
        """All WorkingContext revisions in order, oldest first."""
        return tuple(self._history)

    def __len__(self) -> int:
        return len(self._history)
