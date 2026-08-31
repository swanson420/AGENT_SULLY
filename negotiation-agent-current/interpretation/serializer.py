"""Boundary serializer for the canonical decision WorkingContext contract."""

from __future__ import annotations
from typing import List
from .dlp import redact
from .models import EpistemicRecord, EpistemicTag
from decision.contracts.decision_package import WorkingContext as CanonicalWorkingContext


class WorkingContextSerializer:
    """Serialize only the canonical WorkingContext; no parallel context schema."""

    def serialize(self, context: CanonicalWorkingContext) -> List[EpistemicRecord]:
        records: List[EpistemicRecord] = []
        for event_id in context.source_event_ids:
            records.append(EpistemicRecord.create(
                tag=EpistemicTag.FACT,
                content=f"Source event: {event_id}",
                confidence=1.0,
                provenance_field="source_event_ids",
            ))
        for key, value in context.raw_payload.items():
            records.append(EpistemicRecord.create(
                tag=EpistemicTag.FACT,
                content=f"{redact(str(key))}: {redact(str(value))}",
                confidence=1.0,
                provenance_field="raw_payload",
            ))
        for unknown in context.unknowns:
            records.append(EpistemicRecord.create(
                tag=EpistemicTag.UNCERTAINTY,
                content=f"Unknown ({redact(unknown.criticality)}): {redact(unknown.description)}",
                confidence=0.0,
                provenance_field="unknowns",
            ))
        for assumption in context.assumptions:
            records.append(EpistemicRecord.create(
                tag=EpistemicTag.ASSUMPTION,
                content=redact(assumption.description),
                confidence=assumption.confidence,
                provenance_field="assumptions",
            ))
        return records
