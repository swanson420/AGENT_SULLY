import dataclasses
from datetime import datetime, timezone
import enum
from typing import get_type_hints
import pytest

from decision.contracts.decision_package import (
    WorkingContext,
    DecisionRecord,
    RouteType,
    ActionType,
    Unknown,
    Assumption,
)
from decision.contracts.blast_radius import (
    BlastRadiusScore,
    ImpactLevel,
    VALID_IMPACT_LEVELS,
)


def test_decision_record_field_reflection_drift_guard() -> None:
    """
    Control Invariant: Enforces strict field reflection parity on DecisionRecord.
    Detects uncalibrated attribute additions, deletions, or type mutations across contracts.
    """
    expected_fields = {
        "route": RouteType,
        "action": ActionType,
        "context": WorkingContext,
        "blast_radius": BlastRadiusScore,
        "gate_results": "Mapping[str, bool]",
        "audit_hash": str,
        "timestamp": datetime,
        "rationale": str,
    }

    actual_fields = {f.name: f.type for f in dataclasses.fields(DecisionRecord)}

    assert set(actual_fields.keys()) == set(expected_fields.keys()), (
        f"DecisionRecord schema drift detected! Drift diff: {set(actual_fields.keys()) ^ set(expected_fields.keys())}"
    )


def test_working_context_field_reflection_drift_guard() -> None:
    """
    Control Invariant: Enforces immutable field composition on WorkingContext.
    """
    expected_fields = {
        "source_event_ids",
        "raw_payload",
        "commitment_level",
        "unknowns",
        "assumptions",
    }

    actual_field_names = {f.name for f in dataclasses.fields(WorkingContext)}
    assert actual_field_names == expected_fields, (
        f"WorkingContext schema drift detected: {actual_field_names ^ expected_fields}"
    )


def test_blast_radius_dimension_drift_guard() -> None:
    """
    Control Invariant: Enforces the exact 5-dimensional ontology of BlastRadiusScore.
    """
    expected_dimensions = {
        "reversibility",
        "cost",
        "relationship_impact",
        "commitment",
        "external_visibility",
    }

    actual_dimensions = {f.name for f in dataclasses.fields(BlastRadiusScore)}
    assert actual_dimensions == expected_dimensions, (
        f"BlastRadiusScore dimension drift detected: {actual_dimensions ^ expected_dimensions}"
    )


def test_action_and_route_enum_invariants() -> None:
    """
    Control Invariant: Enum members must remain closed and strictly enumerated.
    """
    expected_routes = {"ACT_SILENTLY", "BOUNCE_DOMAIN", "BOUNCE_META_ESCALATED"}
    actual_routes = {m.name for m in RouteType}
    assert actual_routes == expected_routes

    expected_actions = {
        "QUERY_INFO",
        "EXECUTE_QUERY",
        "MUTATE_STATE",
        "TERMINATE_SYSTEM",
        "OVERRIDE_SECURITY",
        "DEPLOY_PAYLOAD",
        "PURGE_RECORDS",
    }
    actual_actions = {m.name for m in ActionType}
    assert actual_actions == expected_actions
