import dataclasses
from datetime import datetime, timezone
import random
from typing import Any, Dict, List, Tuple
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


def _generate_fuzzed_payload(rng: random.Random, depth: int = 0) -> Any:
    """Recursively constructs randomized payload topologies for contract fuzz testing."""
    if depth > 3:
        return rng.choice(["leaf_str", 42, 3.1415, True, None])

    topology_type = rng.choice(["dict", "list", "primitive", "set"])
    if topology_type == "dict":
        return {
            f"k_{rng.randint(1, 10)}": _generate_fuzzed_payload(rng, depth + 1)
            for _ in range(rng.randint(1, 4))
        }
    elif topology_type == "list":
        return [_generate_fuzzed_payload(rng, depth + 1) for _ in range(rng.randint(1, 4))]
    elif topology_type == "set":
        return {f"val_{rng.randint(1, 10)}" for _ in range(rng.randint(1, 3))}
    else:
        return rng.choice(["fuzz_val", 100, 0.001, False, None])


def test_250_trial_decision_record_contract_invariant_fuzz() -> None:
    """
    Control Invariant: 250-trial invariant fuzz suite ensuring DecisionRecord.validate()
    strictly enforces typing, non-empty rationales, valid 64-char hex hashes, and calibrated
    5D blast radius scores under randomized mutations.
    """
    rng = random.Random(0xDEADBEEF)
    impact_levels = sorted(list(VALID_IMPACT_LEVELS))

    for trial in range(250):
        context = WorkingContext(
            source_event_ids=(f"evt-fuzz-{trial}",),
            raw_payload=_generate_fuzzed_payload(rng),
            commitment_level=rng.choice(impact_levels),
            unknowns=(
                Unknown(
                    description=f"Unknown fuzz {trial}",
                    criticality=rng.choice(["LOW", "MEDIUM", "HIGH", "CRITICAL"]),
                    resolution_precedent=None,
                ),
            ),
            assumptions=(
                Assumption(
                    description=f"Assumption fuzz {trial}",
                    confidence=rng.uniform(0.0, 1.0),
                    grounded=rng.choice([True, False]),
                ),
            ),
        )

        blast = BlastRadiusScore(
            reversibility=rng.choice(impact_levels),  # type: ignore[arg-type]
            cost=rng.choice(impact_levels),  # type: ignore[arg-type]
            relationship_impact=rng.choice(impact_levels),  # type: ignore[arg-type]
            commitment=rng.choice(impact_levels),  # type: ignore[arg-type]
            external_visibility=rng.choice(impact_levels),  # type: ignore[arg-type]
        )

        record = DecisionRecord(
            route=rng.choice(list(RouteType)),
            action=rng.choice(list(ActionType)),
            context=context,
            blast_radius=blast,
            gate_results={"fuzz_gate": rng.choice([True, False])},
            audit_hash=f"{trial:064x}",
            timestamp=datetime.now(timezone.utc),
            rationale=f"Fuzz trial {trial} nominal verification.",
        )

        record.validate()

        defect_mode = trial % 5
        if defect_mode == 0:
            bad_record = dataclasses.replace(record, audit_hash="tooshort")
            with pytest.raises(ValueError, match="Audit hash must be a 64-character"):
                bad_record.validate()

        elif defect_mode == 1:
            bad_record = dataclasses.replace(record, rationale="")
            with pytest.raises(ValueError, match="Rationale must be a non-empty string"):
                bad_record.validate()

        elif defect_mode == 2:
            bad_blast = BlastRadiusScore(
                reversibility="INVALID_SEVERITY",  # type: ignore[arg-type]
                cost="LOW",
                relationship_impact="LOW",
                commitment="LOW",
                external_visibility="LOW",
            )
            bad_record = dataclasses.replace(record, blast_radius=bad_blast)
            with pytest.raises(ValueError, match="invalid impact level"):
                bad_record.validate()

        elif defect_mode == 3:
            bad_record = dataclasses.replace(record, timestamp="2026-08-20T00:00:00Z")  # type: ignore[arg-type]
            with pytest.raises(ValueError, match="Timestamp must be a datetime instance"):
                bad_record.validate()

        elif defect_mode == 4:
            bad_record = dataclasses.replace(record, gate_results=["not", "a", "map"])  # type: ignore[arg-type]
            with pytest.raises(ValueError, match="Gate results must be a mapping"):
                bad_record.validate()
