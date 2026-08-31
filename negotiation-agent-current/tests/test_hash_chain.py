from ledger.hash_chain import chain_hash


def test_chain_hash_is_deterministic_for_equivalent_mappings():
    left = {"b": 2, "a": 1}
    right = {"a": 1, "b": 2}
    assert chain_hash("prev", left) == chain_hash("prev", right)


def test_chain_hash_changes_when_parent_hash_changes():
    payload = {"event": "evt-1", "value": 1}
    assert chain_hash("parent-a", payload) != chain_hash("parent-b", payload)


def test_chain_hash_changes_when_payload_changes():
    assert chain_hash("parent", {"value": 1}) != chain_hash("parent", {"value": 2})


def test_chain_hash_returns_sha256_hex_digest():
    digest = chain_hash("", {"value": 1})
    assert len(digest) == 64
    int(digest, 16)
