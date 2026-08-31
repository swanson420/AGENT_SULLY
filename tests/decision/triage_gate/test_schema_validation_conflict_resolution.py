from datetime import datetime, timezone
from typing import Any, Dict, List
import pytest

from decision.triage_gate.conflict_resolution import (
    ConflictResolutionEngine,
    ConflictResolutionStatus,
    TagKind,
)


def test_conflict_resolution_rejects_missing_mandatory_keys() -> None:
    """
    Control Invariant: Any raw tag missing one or more mandatory schema keys
    triggers an immediate SCHEMA_VIOLATION_BOUNCE without raising an unhandled exception.
    """
    incomplete_tags = [
        {
            "tag_id": "tag-incomplete-01",
            "domain": "storage",
            "parameter": "retention_days",
            "value": 30,
            "timestamp": "2026-08-20T10:00:00Z",
            "source_event_id": "evt-schema-01",
        }
    ]

    result = ConflictResolutionEngine.resolve_conflicts(
        raw_tags=incomplete_tags,
        known_event_ids=["evt-schema-01"],
    )

    assert result.status == ConflictResolutionStatus.SCHEMA_VIOLATION_BOUNCE
    assert len(result.resolved_tags) == 0
    assert "Schema validation error" in result.details
    assert "kind" in result.details


def test_conflict_resolution_rejects_invalid_tag_kind() -> None:
    """
    Control Invariant: TagKind values outside calibrated enumerations
    (CONSTRAINT, PREFERENCE) trigger SCHEMA_VIOLATION_BOUNCE.
    """
    invalid_kind_tags = [
        {
            "tag_id": "tag-bad-kind",
            "kind": "ARBITRARY_DIRECTIVE",
            "domain": "security",
            "parameter": "tls_version",
            "value": "1.3",
            "timestamp": "2026-08-20T10:00:00Z",
            "source_event_id": "evt-schema-02",
        }
    ]

    result = ConflictResolutionEngine.resolve_conflicts(
        raw_tags=invalid_kind_tags,
        known_event_ids=["evt-schema-02"],
    )

    assert result.status == ConflictResolutionStatus.SCHEMA_VIOLATION_BOUNCE
    assert "Unrecognized TagKind value" in result.details


def test_conflict_resolution_rejects_untraceable_source_event_id() -> None:
    """
    Control Invariant: A well-formed tag whose source_event_id is not anchored
    in the known event collection triggers UNTRACEABLE_BOUNCE.
    """
    untraceable_tags = [
        {
            "tag_id": "tag-valid-schema",
            "kind": "CONSTRAINT",
            "domain": "compute",
            "parameter": "max_concurrency",
            "value": 16,
            "timestamp": "2026-08-20T10:00:00Z",
            "source_event_id": "evt-foreign-999",
        }
    ]

    result = ConflictResolutionEngine.resolve_conflicts(
        raw_tags=untraceable_tags,
        known_event_ids=["evt-authorized-001", "evt-authorized-002"],
    )

    assert result.status == ConflictResolutionStatus.UNTRACEABLE_BOUNCE
    assert len(result.unresolved_tags) == 1
    assert "not found in known event IDs" in result.details


def test_conflict_resolution_rejects_non_sequence_container() -> None:
    """
    Control Invariant: Passing a non-sequence structure as raw_tags fails closed
    to SCHEMA_VIOLATION_BOUNCE.
    """
    malformed_input = {"not": "a_sequence"}

    result = ConflictResolutionEngine.resolve_conflicts(
        raw_tags=malformed_input,  # type: ignore[arg-type]
        known_event_ids=["evt-01"],
    )

    assert result.status == ConflictResolutionStatus.SCHEMA_VIOLATION_BOUNCE
    assert "must be provided as a sequence container" in result.details
