from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import MagicMock
import pytest

from decision.contracts.decision_package import (
    WorkingContext,
    DecisionRecord,
    RouteType,
    ActionType,
    Unknown,
)
from decision.contracts.blast_radius import BlastRadiusScore
from decision.triage_gate.stages.stage2_resolvability import StrictResolvabilityStage


def test_stage2_resolvability_resolves_unknown_from_ledger_precedent() -> None:
    """
    Control Invariant: Unknown records lacking precedent are updated when the
    ledger event contains an explicit matching precedent mapping.
    """
    stage = StrictResolvabilityStage()
    mock_ledger = MagicMock()

    mock_ledger.get_event.return_value = {
        "event_id": "evt-res-01",
        "payload": {},
        "precedents": {
            "Is batching enabled for region us-east?": "PRECEDENT: Enabled by default in ADR-002",
        },
    }

    context = WorkingContext(
        source_event_ids=("evt-res-01",),
        raw_payload={},
        commitment_level="LOW",
        unknowns=(
            Unknown(
                description="Is batching enabled for region us-east?",
                criticality="HIGH",
                resolution_precedent=None,
            ),
        ),
        assumptions=(),
    )

    resolved_context = stage.execute(context, mock_ledger)

    assert len(resolved_context.unknowns) == 1
    assert resolved_context.unknowns[0].resolution_precedent == "PRECEDENT: Enabled by default in ADR-002"


def test_stage2_resolvability_surfaces_conflict_resolution_fault_as_critical_unknown() -> None:
    """
    Control Invariant: When raw context tags result in a conflict resolution failure
    (e.g., VIOLATED_CONSTRAINT_BOUNCE), Stage 2 captures the defect as a CRITICAL unknown,
    guaranteeing fail-closed execution in downstream routing.
    """
    stage = StrictResolvabilityStage()
    mock_ledger = MagicMock()

    conflicting_tags_payload = {
        "context_tags": [
            {
                "tag_id": "tag-c1",
                "kind": "CONSTRAINT",
                "domain": "telemetry",
                "parameter": "retention",
                "value": "7d",
                "timestamp": "2026-08-20T10:00:00Z",
                "source_event_id": "evt-res-02",
            },
            {
                "tag_id": "tag-c2",
                "kind": "CONSTRAINT",
                "domain": "telemetry",
                "parameter": "retention",
                "value": "30d",
                "timestamp": "2026-08-20T11:00:00Z",
                "source_event_id": "evt-res-02",
            },
        ]
    }

    context = WorkingContext(
        source_event_ids=("evt-res-02",),
        raw_payload=conflicting_tags_payload,
        commitment_level="LOW",
        unknowns=(),
        assumptions=(),
    )

    resolved_context = stage.execute(context, mock_ledger)

    assert len(resolved_context.unknowns) == 1
    surfaced = resolved_context.unknowns[0]
    assert surfaced.criticality == "CRITICAL"
    assert "Conflict Resolution Fault [VIOLATED_CONSTRAINT_BOUNCE]" in surfaced.description
    assert surfaced.resolution_precedent is None
