"""
config.py
Centralized, immutable configuration baseline for the interpretation/ subsystem.
"""

from __future__ import annotations
from pydantic import BaseModel, Field, ConfigDict


class ExtractionConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    max_input_chars: int = Field(default=16_000)
    max_extracted_items: int = Field(default=200)


class PremiseConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    max_premises: int = Field(default=200)
    confidence_mutation: float = Field(default=0.85)
    confidence_tool_usage: float = Field(default=0.80)
    confidence_causality: float = Field(default=0.75)
    confidence_scale: float = Field(default=0.70)
    confidence_declarative_claim: float = Field(default=0.50)
    confidence_dependency: float = Field(default=0.90)


class DecouplerConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    high_coupling_ceiling: float = Field(default=0.85)
    baseline_coupling: float = Field(default=0.50)
    dependency_coupling_boost: float = Field(default=0.25)
    premise_confidence_penalty_threshold: float = Field(default=0.80)
    premise_confidence_penalty_amount: float = Field(default=0.15)


class AmbiguityConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    max_ambiguity_items: int = Field(default=200)
    low_confidence_premise_threshold: float = Field(default=0.75)


class ChallengeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    base_risk: float = Field(default=0.10)
    contradiction_risk_boost: float = Field(default=0.35)
    medium_ambiguity_weight: float = Field(default=0.08)
    max_medium_ambiguity_risk: float = Field(default=0.25)
    method_constraint_risk_boost: float = Field(default=0.15)
    low_confidence_premise_weight: float = Field(default=0.08)
    max_low_confidence_risk: float = Field(default=0.25)
    high_risk_premise_threshold: float = Field(default=0.80)


class PolicyGateConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    default_max_risk_threshold: float = Field(default=0.70)
    allow_degraded_commit_default: bool = Field(default=False)


class PipelineSystemConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    premise: PremiseConfig = Field(default_factory=PremiseConfig)
    decoupler: DecouplerConfig = Field(default_factory=DecouplerConfig)
    ambiguity: AmbiguityConfig = Field(default_factory=AmbiguityConfig)
    challenge: ChallengeConfig = Field(default_factory=ChallengeConfig)
    policy_gate: PolicyGateConfig = Field(default_factory=PolicyGateConfig)


DEFAULT_CONFIG = PipelineSystemConfig()
