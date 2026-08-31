from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Mapping, Optional, Tuple

from decision.contracts.blast_radius import BlastRadiusScore


class RouteType(Enum):
    ACT_SILENTLY = auto()
    BOUNCE_DOMAIN = auto()
    BOUNCE_META_ESCALATED = auto()


class ActionType(Enum):
    QUERY_INFO = auto()
    EXECUTE_QUERY = auto()
    MUTATE_STATE = auto()
    TERMINATE_SYSTEM = auto()
    OVERRIDE_SECURITY = auto()
    DEPLOY_PAYLOAD = auto()
    PURGE_RECORDS = auto()


@dataclass(frozen=True)
class Unknown:
    description: str
    criticality: str
    resolution_precedent: Optional[str] = None

    def __post_init__(self) -> None:
        """Normalize criticality casing at construction, not at every
        call site that happens to check it.

        Found via direct execution, not inspection: stage4_routing.py's
        interpretation_stable gate checks
        `u.criticality in ("CRITICAL", "HIGH")` -- exact string match,
        case-sensitive. stage1_surfacing.py only upper()s criticality for
        unknowns it parses itself from a raw payload dict; an Unknown
        constructed directly (as every scenario fixture, every test, and
        any future caller not routing through that one parsing path does)
        keeps whatever casing it was given. A real unresolved HIGH-risk
        unknown built as criticality="high" silently passed the gate and
        reached ACT_SILENTLY when tested end to end -- confirmed by
        executing StrictRoutingStage directly before this fix existed.
        Normalizing here closes it at the source instead of patching every
        comparison site (stage4 today, potentially more callers later).
        """
        object.__setattr__(self, "criticality", str(self.criticality).upper())


@dataclass(frozen=True)
class Assumption:
    description: str
    confidence: float
    grounded: bool = False


@dataclass(frozen=True)
class RecursionMetadata:
    """Tracks how many bounded loop-back passes a decision has undergone.

    Lives here, not in decision/triage_gate/ -- an earlier generation of
    this same concept lived directly inside
    decision/triage_gate/decision_package.py and was deliberately deleted
    (see decision/contracts/README.md's "Why this folder exists" note),
    not migrated, because nothing depended on it at the time. Something
    now does: decision/triage_gate/recursion_guard.py's authorize_next_pass
    imported it from that already-deleted path, which fails at import time.
    This is the current, real definition -- recursion_guard.py's import
    was pointing at a ghost of a file that no longer exists.
    """
    recursion_depth: int
    max_recursion_depth: int
    parent_decision_id: Optional[str] = None


@dataclass(frozen=True)
class WorkingContext:
    source_event_ids: Tuple[str, ...]
    raw_payload: Mapping[str, Any]
    commitment_level: Optional[str] = None
    unknowns: Tuple[Unknown, ...] = field(default_factory=tuple)
    assumptions: Tuple[Assumption, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DecisionRecord:
    route: RouteType
    action: ActionType
    context: WorkingContext
    blast_radius: BlastRadiusScore
    gate_results: Mapping[str, bool]
    audit_hash: str
    timestamp: datetime
    rationale: str

    def validate(self) -> None:
        if not isinstance(self.route, RouteType):
            raise ValueError(f"Invalid route type: {type(self.route).__name__}")
        if not isinstance(self.action, ActionType):
            raise ValueError(f"Invalid action type: {type(self.action).__name__}")
        if not isinstance(self.context, WorkingContext):
            raise ValueError(f"Invalid context structure: {type(self.context).__name__}")
        if not isinstance(self.blast_radius, BlastRadiusScore):
            raise ValueError(f"Invalid blast radius structure: {type(self.blast_radius).__name__}")
        self.blast_radius.validate()
        if not isinstance(self.gate_results, Mapping):
            raise ValueError(f"Gate results must be a mapping: {type(self.gate_results).__name__}")
        if not isinstance(self.audit_hash, str) or len(self.audit_hash) != 64:
            raise ValueError("Audit hash must be a 64-character hexadecimal SHA-256 string.")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("Timestamp must be a datetime instance.")
        if not self.rationale or not isinstance(self.rationale, str):
            raise ValueError("Rationale must be a non-empty string.")
