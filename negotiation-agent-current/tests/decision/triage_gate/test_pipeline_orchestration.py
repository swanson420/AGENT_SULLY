# tests/decision/triage_gate/test_pipeline_orchestration.py
from datetime import datetime, timezone
import hashlib
from typing import Mapping
from unittest.mock import MagicMock
import pytest

from decision.contracts.decision_package import (
    WorkingContext,
    DecisionRecord,
    RouteType,
    ActionType,
    RecursionMetadata,
)
from decision.contracts.blast_radius import BlastRadiusScore
from decision.triage_gate.config import DEFAULT_CONFIG, TriageGateConfig
from decision.triage_gate.provenance import ProvenanceEngine
from decision.triage_gate.recursion_guard import RecursionCapExceeded, authorize_next_pass
from decision.triage_gate.triage import TriagePipelineOrchestrator
from decision.triage_gate.stages.stage1_surfacing import StrictUnknownSurfacingStage
from decision.triage_gate.stages.stage2_resolvability import StrictResolvabilityStage
from decision.triage_gate.stages.stage3_blast_radius import StrictBlastRadiusStage
from decision.triage_gate.stages.stage4_routing import StrictRoutingStage
from decision.triage_gate.stages.stage5_audit import StrictAuditStage


# This file previously had zero test functions -- collection-only imports,
# same gap as tests/decision/triage_gate/test_mock_ledger.py before it was
# fixed. Also imported a name (MaxRecursionDepthExceeded) that never
# existed anywhere in the codebase; recursion_guard.py's real exception is
# RecursionCapExceeded, unchanged since it was written. Fixed the import
# and added real coverage below rather than just patching the name.
#
# Worth knowing while reading these: authorize_next_pass() has zero real
# callers anywhere in the pipeline right now (confirmed by grep before
# writing this) -- these tests exercise the function directly, not through
# TriagePipelineOrchestrator, because nothing wires the two together yet.
# Same disconnection pattern already flagged for MetaGate.

def test_authorize_next_pass_grants_authorization_within_cap():
    meta = RecursionMetadata(recursion_depth=0, max_recursion_depth=1, parent_decision_id=None)
    auth = authorize_next_pass(meta)
    assert auth.authorized_depth == 1
    assert auth.parent_decision_id is None


def test_authorize_next_pass_raises_at_cap():
    meta = RecursionMetadata(recursion_depth=1, max_recursion_depth=1, parent_decision_id="dec-1")
    with pytest.raises(RecursionCapExceeded, match="exceeds max_recursion_depth"):
        authorize_next_pass(meta)


def test_authorize_next_pass_preserves_parent_decision_id():
    meta = RecursionMetadata(recursion_depth=0, max_recursion_depth=2, parent_decision_id="dec-parent")
    auth = authorize_next_pass(meta)
    assert auth.parent_decision_id == "dec-parent"

