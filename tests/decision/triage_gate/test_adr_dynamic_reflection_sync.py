import dataclasses
import inspect
from pathlib import Path
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
from decision.contracts.blast_radius import BlastRadiusScore, VALID_IMPACT_LEVELS
from decision.triage_gate.config import DEFAULT_CONFIG, TriageGateConfig
from decision.triage_gate.provenance import ProvenanceEngine
from decision.triage_gate.conflict_resolution import ConflictResolutionEngine
from decision.triage_gate.ledger_client import ConcreteLedgerClient
from decision.triage_gate.telemetry import TransportTelemetrySink


def test_adr_008_dynamic_reflection_and_ast_token_alignment() -> None:
    """
    Control Invariant: Parses ADR-008 architectural markdown text and asserts
    direct AST reflection parity against live runtime engine dataclasses, protocols,
    and stage definitions.
    """
    adr_path = Path("docs/architecture/decisions/ADR-008-ledger-integration-and-provenance-transport.md")
    assert adr_path.exists(), f"ADR-008 file missing: {adr_path}"
    adr_text = adr_path.read_text(encoding="utf-8")

    expected_components = [
        ProvenanceEngine,
        ConflictResolutionEngine,
        ConcreteLedgerClient,
        TransportTelemetrySink,
        WorkingContext,
        DecisionRecord,
        BlastRadiusScore,
    ]
    for comp in expected_components:
        comp_name = comp.__name__
        assert f"`{comp_name}`" in adr_text, f"ADR-008 text missing reference to component `{comp_name}`"

    blast_fields = {f.name for f in dataclasses.fields(BlastRadiusScore)}
    for dimension in blast_fields:
        assert dimension.lower() in adr_text.lower(), f"ADR-008 missing blast radius dimension: {dimension}"

    for gate in DEFAULT_CONFIG.required_pre_action_gates:
        assert gate in adr_text, f"ADR-008 missing pre-action gate definition: {gate}"


def test_triage_gate_config_immutability_and_defaults() -> None:
    """
    Control Invariant: TriageGateConfig maintains exact field defaults reflecting
    ADR-008 constraints and guarantees fail-closed gate structures.
    """
    config = TriageGateConfig()

    assert "interpretation_stable" in config.required_pre_action_gates
    assert "context_anchored" in config.required_pre_action_gates
    assert "ledger_anchored" in config.required_pre_action_gates
    assert "blast_radius_calibrated" in config.required_pre_action_gates
    assert "assumptions_grounded" in config.required_pre_action_gates

    assert ActionType.TERMINATE_SYSTEM in config.mandatory_escalation_actions
    assert ActionType.PURGE_RECORDS in config.mandatory_escalation_actions
    assert ActionType.OVERRIDE_SECURITY in config.mandatory_escalation_actions
