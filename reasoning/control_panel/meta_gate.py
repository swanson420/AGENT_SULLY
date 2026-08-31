"""Meta-uncertainty classification and conservative resolution."""
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from decision.contracts.decision_package import ActionType
from decision.triage_gate.conservative_defaults import (
    ConservativeDefault,
    FallbackState,
    conservative_default_for,
)


class UncertaintyKind(Enum):
    DOMAIN = auto()
    META = auto()


@dataclass(frozen=True)
class MetaResolution:
    kind: UncertaintyKind
    fallback: ConservativeDefault
    interrupted: bool


class MetaGate:
    """Classifies uncertainty and resolves meta-uncertainty conservatively."""

    @staticmethod
    def classify(*, domain_uncertain: bool = False, meta_uncertain: bool = False) -> Optional[UncertaintyKind]:
        if domain_uncertain:
            return UncertaintyKind.DOMAIN
        if meta_uncertain:
            return UncertaintyKind.META
        return None

    @staticmethod
    def resolve_uncertainty(action: ActionType, kind: UncertaintyKind) -> MetaResolution:
        if kind is UncertaintyKind.DOMAIN:
            # Domain uncertainty requires a human bounce; there is no silent fallback.
            fallback = conservative_default_for(action)
            return MetaResolution(kind, fallback, interrupted=True)

        if kind is not UncertaintyKind.META:
            raise ValueError(f"Unsupported uncertainty kind: {kind!r}")

        fallback = conservative_default_for(action)
        return MetaResolution(
            kind=kind,
            fallback=fallback,
            interrupted=fallback.state is FallbackState.FORCED_ESCALATION,
        )
