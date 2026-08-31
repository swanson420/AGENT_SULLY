from datetime import datetime, timezone
from typing import Any, Dict, List
import pytest

from decision.triage_gate.conflict_resolution import (
    ConflictResolutionEngine,
    ConflictResolutionStatus,
    TagKind,
)


def test_conflict_resolution_preference_recency() -> None:
    """
    Control Invariant: For conflicting soft preferences on the same (domain, parameter),
    the entry with the newest UTC timestamp takes precedence.
    """
    raw_tags = [
        {
            "tag_id": "tag-pref-old",
            "kind": "PREFERENCE",
            "domain": "compute",
            "parameter": "region",
            "value": "us-east-1",
            "timestamp": "2026-08-20T10:00:00Z",
            "source_event_id": "evt-01",
        },
        {
            "tag_id": "tag-pref-new",
            "kind": "PREFERENCE",
            "domain": "compute",
            "parameter": "region",
            "value": "us-west-2",
            "timestamp": "2026-08-20T12:00:00Z",
            "source_event_id": "evt-01",
        },
    ]

    result = ConflictResolutionEngine.resolve_conflicts(
        raw_tags=raw_tags,
        known_event_ids=["evt-01"],
    )

    assert result.status == ConflictResolutionStatus.RESOLVED
    assert len(result.resolved_tags) == 1
    assert result.resolved_tags[0].tag_id == "tag-pref-new"
    assert result.resolved_tags[0].value == "us-west-2"


def test_conflict_resolution_constraint_supersedes_newer_preference() -> None:
    """
    Control Invariant: Hard constraints strictly supersede soft preferences
    on the same parameter, even if the preference has a newer timestamp.
    """
    raw_tags = [
        {
            "tag_id": "tag-hard-constraint",
            "kind": "CONSTRAINT",
            "domain": "network",
            "parameter": "max_connections",
            "value": 100,
            "timestamp": "2026-08-20T08:00:00Z",
            "source_event_id": "evt-01",
        },
        {
            "tag_id": "tag-soft-pref",
            "kind": "PREFERENCE",
            "domain": "network",
            "parameter": "max_connections",
            "value": 500,
            "timestamp": "2026-08-20T15:00:00Z",
            "source_event_id": "evt-01",
        },
    ]

    result = ConflictResolutionEngine.resolve_conflicts(
        raw_tags=raw_tags,
        known_event_ids=["evt-01"],
    )

    assert result.status == ConflictResolutionStatus.RESOLVED
    assert len(result.resolved_tags) == 1
    assert result.resolved_tags[0].tag_id == "tag-hard-constraint"
    assert result.resolved_tags[0].value == 100


def test_conflict_resolution_conflicting_constraints_fail_closed() -> None:
    """
    Control Invariant: Multiple constraints with differing values for the same
    parameter cannot be reconciled by recency and must trigger VIOLATED_CONSTRAINT_BOUNCE.
    """
    raw_tags = [
        {
            "tag_id": "tag-const-1",
            "kind": "CONSTRAINT",
            "domain": "storage",
            "parameter": "encryption",
            "value": "AES256",
            "timestamp": "2026-08-20T10:00:00Z",
            "source_event_id": "evt-01",
        },
        {
            "tag_id": "tag-const-2",
            "kind": "CONSTRAINT",
            "domain": "storage",
            "parameter": "encryption",
            "value": "CHACHA20",
            "timestamp": "2026-08-20T11:00:00Z",
            "source_event_id": "evt-01",
        },
    ]

    result = ConflictResolutionEngine.resolve_conflicts(
        raw_tags=raw_tags,
        known_event_ids=["evt-01"],
    )

    assert result.status == ConflictResolutionStatus.VIOLATED_CONSTRAINT_BOUNCE
    assert len(result.unresolved_tags) == 2
    assert "Conflicting constraints detected" in result.details


def test_conflict_resolution_simultaneous_timestamp_collision_fails_closed() -> None:
    """
    Control Invariant: Multiple preference tags on the same parameter with identical
    timestamps and differing values fail closed with AMBIGUOUS_BOUNCE.
    """
    raw_tags = [
        {
            "tag_id": "tag-coll-1",
            "kind": "PREFERENCE",
            "domain": "ui",
            "parameter": "theme",
            "value": "dark",
            "timestamp": "2026-08-20T12:00:00Z",
            "source_event_id": "evt-01",
        },
        {
            "tag_id": "tag-coll-2",
            "kind": "PREFERENCE",
            "domain": "ui",
            "parameter": "theme",
            "value": "light",
            "timestamp": "2026-08-20T12:00:00Z",
            "source_event_id": "evt-01",
        },
    ]

    result = ConflictResolutionEngine.resolve_conflicts(
        raw_tags=raw_tags,
        known_event_ids=["evt-01"],
    )

    assert result.status == ConflictResolutionStatus.AMBIGUOUS_BOUNCE
    assert len(result.unresolved_tags) == 2
    assert "Ambiguous collision" in result.details
