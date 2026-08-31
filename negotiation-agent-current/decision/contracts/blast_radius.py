from dataclasses import dataclass
from typing import Literal

ImpactLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]

VALID_IMPACT_LEVELS = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})


@dataclass(frozen=True)
class BlastRadiusScore:
    reversibility: ImpactLevel
    cost: ImpactLevel
    relationship_impact: ImpactLevel
    commitment: ImpactLevel
    external_visibility: ImpactLevel

    def validate(self) -> None:
        for dim_name in (
            "reversibility", "cost", "relationship_impact",
            "commitment", "external_visibility",
        ):
            val = getattr(self, dim_name)
            if val not in VALID_IMPACT_LEVELS:
                raise ValueError(
                    f"Blast radius dimension '{dim_name}' has invalid impact level '{val}'. "
                    f"Must be one of {sorted(VALID_IMPACT_LEVELS)}."
                )

    def to_ordinal_map(self) -> dict[str, int]:
        weights = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        return {
            "reversibility": weights[self.reversibility],
            "cost": weights[self.cost],
            "relationship_impact": weights[self.relationship_impact],
            "commitment": weights[self.commitment],
            "external_visibility": weights[self.external_visibility],
        }


@dataclass(frozen=True)
class DivergenceResult:
    """Result of check_divergence(). diverged=True must be folded into
    gate_results and treated as domain uncertainty (bounce) -- never
    silently resolved, per decision/triage_gate/README.md's fix #5."""
    diverged: bool
    flagged_dimensions: tuple[str, ...]
    rationale: str


def check_divergence(blast_radius: BlastRadiusScore) -> DivergenceResult:
    """Guards against self-scoring bias: the `commitment` dimension is
    the one field of a BlastRadiusScore that most directly reflects how
    seriously an action is being taken. If any of the other four
    dimensions is scored *more* severe than `commitment`, that's exactly
    the failure mode named in decision/triage_gate/README.md's fix #5 --
    "a HIGH-commitment action... quietly scored as LOW-risk" -- except
    inverted: here it's the commitment dimension itself quietly
    understating what the other four measured dimensions already show.
    Zero tolerance: any single dimension exceeding `commitment` flags it.

    Design note on why this doesn't use a 0-5 "commitment level": the
    README describes commitment level on a 0-5 scale, which is
    action/commitment_gradient.py's scale -- but that module lives in
    action/, one layer above decision/triage_gate/. Importing it here
    would create the same upward-dependency violation that was fixed in
    ledger/ledger.py earlier (decision/contracts/ -> action/ is backwards).
    This uses BlastRadiusScore's own `commitment` dimension instead --
    already present, already in the same LOW/MEDIUM/HIGH/CRITICAL
    vocabulary as every other dimension here, no new coupling.
    """
    blast_radius.validate()
    ordinal_map = blast_radius.to_ordinal_map()
    commitment_ordinal = ordinal_map["commitment"]

    other_dims = {k: v for k, v in ordinal_map.items() if k != "commitment"}
    flagged = tuple(sorted(k for k, v in other_dims.items() if v > commitment_ordinal))

    if flagged:
        return DivergenceResult(
            diverged=True,
            flagged_dimensions=flagged,
            rationale=(
                f"commitment dimension ('{blast_radius.commitment}', ordinal "
                f"{commitment_ordinal}) understates severity already reflected "
                f"in: {', '.join(flagged)}."
            ),
        )
    return DivergenceResult(
        diverged=False,
        flagged_dimensions=(),
        rationale="commitment dimension is consistent with the other measured dimensions.",
    )
