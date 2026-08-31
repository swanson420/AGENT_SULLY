"""working-context/epistemic_tags.py

working-context/README.md promises: "Every claim carries an epistemic
tag: [F] fact, [I] inference, [A] assumption, [U] uncertain, [Q] open
question." That vocabulary already has exactly one canonical definition —
interpretation.models.EpistemicTag / EpistemicRecord — used by
interpretation/serializer.py to turn a WorkingContext into tagged claims.

This module re-exports that canonical definition rather than declaring a
second one. A second EpistemicTag enum living here would be exactly the
kind of duplicate-structure risk this module needs to avoid: two enums
with the same [F]/[I]/[A]/[U]/[Q] vocabulary that could silently drift
out of sync with no test catching it (contrast with WorkingContext itself,
which has tests/test_interpretation_imports.py guarding single-definition
status — no equivalent guard exists yet for EpistemicTag).

NOTE — coupling direction worth a second look: this makes working-context/
depend on interpretation/, which is a lateral dependency, not strictly
backward like the ledger/decision_layer coupling that was corrected
earlier, but still worth flagging under the same discipline. If
working-context/ and interpretation/ are meant to be independent siblings
(both consumers of decision.contracts, neither depending on the other),
the more robust long-term fix is promoting EpistemicTag/EpistemicRecord
into decision/contracts/ alongside WorkingContext, and having both
interpretation/ and working-context/ import from there instead. Not done
here — that's a schema-ownership decision, not a wiring one, and moving it
would touch interpretation/serializer.py and its passing tests. Left as an
explicit open item rather than decided by default.
"""

from __future__ import annotations

from interpretation.models import EpistemicRecord, EpistemicTag

__all__ = ["EpistemicTag", "EpistemicRecord"]
