from ledger.ledger import Ledger
from decision.triage_gate.provenance import ProvenanceEngine


def test_append_builds_contiguous_hash_chain():
    ledger = Ledger()
    first = ledger.append("evt-1", {"value": 1})
    second = ledger.append("evt-2", {"value": 2})

    entries = ledger.entries
    assert entries[0]["prev_hash"] == ""
    assert entries[0]["hash"] == first
    assert entries[1]["prev_hash"] == first
    assert entries[1]["hash"] == second


def test_append_rejects_corrupted_chain_before_persisting():
    ledger = Ledger()
    ledger.append("evt-1", {"value": 1})
    ledger._entries[0]["payload"]["value"] = 999

    before = len(ledger.entries)
    try:
        ledger.append("evt-2", {"value": 2})
    except ValueError as exc:
        assert "continuity" in str(exc)
    else:
        raise AssertionError("corrupted chain was accepted")

    assert len(ledger.entries) == before
    assert ledger.get_event("evt-2") is None


def test_append_rejects_duplicate_event_id_without_persisting():
    ledger = Ledger()
    ledger.append("evt-1", {"value": 1})
    before = ledger.entries

    try:
        ledger.append("evt-1", {"value": 2})
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate event ID was accepted")

    assert ledger.entries == before


def test_entries_are_snapshots_and_cannot_mutate_stored_payload():
    ledger = Ledger()
    ledger.append("evt-1", {"nested": {"value": 1}})

    snapshot = ledger.entries
    snapshot[0]["payload"]["nested"]["value"] = 999

    stored = ledger.get_event("evt-1")
    assert stored["payload"]["nested"]["value"] == 1


def test_provenance_verification_matches_canonical_provenance_engine():
    ledger = Ledger()
    ledger.append("evt-b", {"value": 2})
    ledger.append("evt-a", {"value": 1})

    events = {eid: ledger.get_event(eid) for eid in ("evt-a", "evt-b")}
    _, expected = ProvenanceEngine.aggregate_event_payloads(
        ("evt-b", "evt-a"), events
    )

    assert ledger.verify_provenance(("evt-b", "evt-a"), expected) is True
    assert ledger.verify_provenance(("evt-b", "evt-a"), "0" * 64) is False
