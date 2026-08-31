# ledger/ — Immutable Event Ledger (also the authority audit reads from)

Append-only, hash-chained. Records what actually happened. Never rewritten.

Entries: user instructions, incoming counterparty messages, agent actions, human decisions, tool results, blast-radius dimensions recorded per decision, commitment level recorded per action, domain/meta bounce tags — each with timestamp + hash of previous entry.

## Audit is a view, not a separate store
`audit_view.py` reads structured decision metadata directly out of ledger entries. There is no independent audit database — a second source of truth for "what happened" is the exact failure mode this split exists to prevent (see operating-standard.md item 2, and Claude #10 on unauditable records).

## Ledger as independent authority (not just the graph's starting node)
`working-context/` and `interpretation/` read FROM this and may hold revisable beliefs, but Triage's step 5 (audit) and the conflict-resolution rule trace claims back to LEDGER entries directly — never to working-context's current summary of them. A claim's source is always checkable here.

## Not built here
- Interpretation of events (that's `working-context/` and `interpretation/`).
- Any mutation or "correction" path. A wrong entry gets a new entry pointing at it, never an edit.

## Open
- Storage backend: in-memory stub for local dev, Firestore for real (`infra/firestore/`) — deferred until after M0, see docs/build-plan.md.

## Build plan — implement `LedgerProtocol`, don't invent a new shape
`decision/triage_gate/base.py` already defines the interface every consumer of this module expects:

```python
class LedgerProtocol(Protocol):
    def get_event(self, event_id: str) -> Optional[Mapping[str, Any]]:
        """Fetch a specific event by ID."""

    def verify_provenance(self, event_ids: Sequence[str], expected_hash: str) -> bool:
        """Verify the cryptographic hash across multiple event payloads."""

    def record_decision_view(self, record: DecisionRecord) -> bool:
        """Commit an audited decision record to the ledger view."""
```

`decision/triage_gate/` is already built against this exact protocol. Build `ledger.py` to satisfy it directly — don't invent different method names or shapes and require a translation layer later.

1. **`hash_chain.py`** — the append-only chain primitive: each entry stores its own hash plus the previous entry's hash, so tampering anywhere breaks every hash after it. No edit or delete method — appending is the only write operation.
2. **`ledger.py`** — the `Ledger` class, in-memory for now (`infra/firestore/` is the real backend, deferred). Implements:
   - `get_event(event_id)` — look up one entry by ID, or `None` if it doesn't exist.
   - `verify_provenance(event_ids, expected_hash)` — fetch the given events, recompute their combined hash the same way `ProvenanceEngine.aggregate_event_payloads()` does (`decision/triage_gate/provenance.py`), and compare against `expected_hash`.
   - `record_decision_view(record)` — append a `DecisionRecord` as a new chained entry; returns `True`/`False` on success/failure, never raises for an ordinary write rejection.
3. **`audit_view.py`** — read-only queries over `ledger.py`'s entries (e.g. "all decisions for this session," "all bounce events"). No new storage, no new write path — every method here just filters/reads what `ledger.py` already holds.

Test against `decision/triage_gate/tests/` fixtures once built — those tests already exercise a `LedgerProtocol`-shaped mock (`ConcreteLedgerClient` + `MockTransportDriver`) and are the closest thing to a spec for exact behavior under retries/failures.
