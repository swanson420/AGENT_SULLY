from datetime import datetime, timezone
import pytest

from decision.triage_gate.conflict_resolution import (
    ConflictResolutionEngine,
    ConflictResolutionStatus,
    TagKind,
)


def test_conflict_resolution_normalizes_mixed_timezone_representations() -> None:
    """
    Control Invariant: Mixed timezone encodings (UTC Zulu string, positive/negative
    ISO offsets, and numeric POSIX epochs) must be normalized into standard UTC datetime
    instances so recency sorting reflects true absolute timeline order.
    """
    raw_tags = [
        {
            "tag_id": "tag-epoch",
            "kind": "PREFERENCE",
            "domain": "telemetry",
            "parameter": "batch_size",
            "value": 100,
            "timestamp": 1787227200.0,
            "source_event_id": "evt-tz-01",
        },
        {
            "tag_id": "tag-offset-plus",
            "kind": "PREFERENCE",
            "domain": "telemetry",
            "parameter": "batch_size",
            "value": 250,
            "timestamp": "2026-08-20T15:00:00+02:00",
            "source_event_id": "evt-tz-01",
        },
        {
            "tag_id": "tag-offset-minus",
            "kind": "PREFERENCE",
            "domain": "telemetry",
            "parameter": "batch_size",
            "value": 50,
            "timestamp": "2026-08-20T06:00:00-05:00",
            "source_event_id": "evt-tz-01",
        },
    ]

    result = ConflictResolutionEngine.resolve_conflicts(
        raw_tags=raw_tags,
        known_event_ids=["evt-tz-01"],
    )

    assert result.status == ConflictResolutionStatus.RESOLVED
    assert len(result.resolved_tags) == 1
    winner = result.resolved_tags[0]
    assert winner.tag_id == "tag-offset-plus"
    assert winner.value == 250
    assert winner.timestamp == datetime(2026, 8, 20, 13, 0, 0, tzinfo=timezone.utc)


def test_conflict_resolution_naive_iso_assumes_utc() -> None:
    """
    Control Invariant: Naive ISO timestamp strings lacking offset designators
    are defensively anchored to UTC rather than local runtime system clock.
    """
    raw_tags = [
        {
            "tag_id": "tag-naive-1",
            "kind": "PREFERENCE",
            "domain": "cache",
            "parameter": "ttl_seconds",
            "value": 300,
            "timestamp": "2026-08-20T10:00:00",
            "source_event_id": "evt-tz-02",
        },
        {
            "tag_id": "tag-naive-2",
            "kind": "PREFERENCE",
            "domain": "cache",
            "parameter": "ttl_seconds",
            "value": 600,
            "timestamp": "2026-08-20T11:00:00",
            "source_event_id": "evt-tz-02",
        },
    ]

    result = ConflictResolutionEngine.resolve_conflicts(
        raw_tags=raw_tags,
        known_event_ids=["evt-tz-02"],
    )

    assert result.status == ConflictResolutionStatus.RESOLVED
    assert len(result.resolved_tags) == 1
    winner = result.resolved_tags[0]
    assert winner.tag_id == "tag-naive-2"
    assert winner.value == 600
    assert winner.timestamp.tzinfo == timezone.utc
    assert winner.timestamp == datetime(2026, 8, 20, 11, 0, 0, tzinfo=timezone.utc)
