# tests/decision/triage_gate/test_nominal_silent_actuation.py
from datetime import datetime, timezone
import pytest

from decision.contracts.decision_package import (
    WorkingContext,
    DecisionRecord,
    RouteType,
    ActionType,
    Assumption,
)
from decision.contracts.blast_radius import BlastRadiusScore
from decision.triage_gate.config import DEFAULT_CONFIG
from decision.triage_gate.provenance import ProvenanceEngine
from decision.triage_gate.triage import TriagePipelineOrchestrator
