"""
models.py
Domain models, enums, and data schemas for the interpretation/ subsystem.
"""

from __future__ import annotations
import hashlib
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class AmbiguityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    BLOCKING = "BLOCKING"


class EpistemicTag(str, Enum):
    FACT = "F"
    INFERENCE = "I"
    ASSUMPTION = "A"
    UNCERTAINTY = "U"
    CHALLENGE = "Q"


class ProvenanceSpan(BaseModel):
    model_config = ConfigDict(frozen=True)
    source_field: str = Field(..., description="Field source: raw_input or ledger")
    start_char: int
    end_char: int
    verbatim_text: str


class ExtractedContext(BaseModel):
    """Stage 1: Strict literal extraction without unverified inferences."""
    model_config = ConfigDict(frozen=True)
    objectives: List[str] = Field(default_factory=list, description="Explicitly stated user goals")
    requirements: List[str] = Field(default_factory=list, description="Explicitly stated functional requirements")
    constraints: List[str] = Field(default_factory=list, description="Hard operational boundaries")
    facts: List[str] = Field(default_factory=list, description="Asserted domain facts")
    dependencies: List[str] = Field(default_factory=list, description="Referenced external systems or dependencies")
    contradictions: List[str] = Field(default_factory=list, description="Direct textual contradictions detected in input")
    is_truncated: bool = Field(default=False, description="Telemetry flag for context budget overrun")


class ExtractedPremise(BaseModel):
    model_config = ConfigDict(frozen=True)
    statement: str = Field(..., description="The unstated axiom or presupposition")
    confidence: float = Field(..., ge=0.0, le=1.0)
    provenance: Optional[ProvenanceSpan] = None
    requires_verification: bool = Field(default=True, description="Flag indicating downstream checking required")


class PremiseRegistry(BaseModel):
    """Stage 1b: Isolated implicit reasoning and epistemic assumptions."""
    model_config = ConfigDict(frozen=True)
    premises: List[ExtractedPremise] = Field(default_factory=list)


class IntentDecoupling(BaseModel):
    """Stage 2a: Separation of core objective from proposed vector with constraint locking."""
    model_config = ConfigDict(frozen=True)
    core_goal: str = Field(..., description="What the user wants to achieve")
    proposed_method: str = Field(..., description="The implementation vector proposed by the user")
    method_is_constraint: bool = Field(..., description="If True, method is locked and non-decoupleable")
    coupling_strength: float = Field(..., ge=0.0, le=1.0)
    alternative_vectors_permissible: bool


class AmbiguityItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    target_token: str
    divergent_meanings: List[str]
    severity: AmbiguityLevel
    blocking_execution: bool


class AmbiguityReport(BaseModel):
    """Stage 2b: Variance and uncertainty quantification."""
    model_config = ConfigDict(frozen=True)
    items: List[AmbiguityItem] = Field(default_factory=list)
    has_blocking_ambiguity: bool = False


class InterpretationChallenge(BaseModel):
    """Stage 3: Competing candidate interpretation and catastrophic failure vector."""
    model_config = ConfigDict(frozen=True)
    competing_interpretation: str = Field(..., description="Strongest plausible alternative understanding")
    failure_scenario: str = Field(..., description="Scenario under which default interpretation fails")
    risk_severity_score: float = Field(..., ge=0.0, le=1.0)


class StageAttestation(BaseModel):
    """
    Proof of what actually happened during one pipeline stage call, computed
    by the trusted orchestrator (engine.py) from the real input and output
    objects it directly observed. This is never supplied or self-reported by
    the stage implementation - a stage implementation is the untrusted party
    here, so nothing about its output includes a 'trust me' field. The
    attestation existing in the chain, with digests the engine itself
    computed, is the proof; there is no separate boolean to spoof.
    """
    model_config = ConfigDict(frozen=True)
    stage_id: str
    input_digest: str
    output_digest: str

    @classmethod
    def generate(
        cls, stage_id: str, input_repr: str, output_model: BaseModel
    ) -> "StageAttestation":
        input_digest = hashlib.sha256(input_repr.encode("utf-8")).hexdigest()
        output_digest = hashlib.sha256(
            output_model.model_dump_json().encode("utf-8")
        ).hexdigest()
        return cls(
            stage_id=stage_id,
            input_digest=input_digest,
            output_digest=output_digest,
        )



class EpistemicRecord(BaseModel):
    """
    Downstream serialization unit consumed by working-context/.
    Combines standardized [TAG] text formatting with full underlying typed metadata.
    """
    model_config = ConfigDict(frozen=True)
    tag: EpistemicTag
    statement: str = Field(..., description="Normalized text payload prefixed with [TAG]")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance_field: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        tag: EpistemicTag,
        content: str,
        confidence: float = 1.0,
        provenance_field: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EpistemicRecord:
        clean_content = content.strip()
        prefixed = f"[{tag.value}] {clean_content}"
        return cls(
            tag=tag,
            statement=prefixed,
            confidence=confidence,
            provenance_field=provenance_field,
            metadata=metadata or {},
        )
