"""Deterministic hash-chain primitive for the in-memory ledger."""

from hashlib import sha256
import json
from typing import Any, Mapping


def _canonical_json(payload: Mapping[str, Any]) -> str:
    """Return the deterministic JSON representation used by the chain."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def chain_hash(prev_hash: str, payload: Mapping[str, Any]) -> str:
    """Hash the previous chain hash together with canonical JSON payload bytes."""
    material = prev_hash + _canonical_json(payload)
    return sha256(material.encode("utf-8")).hexdigest()
