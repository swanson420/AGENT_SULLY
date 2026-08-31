"""Stage 1b: deterministic extraction of implicit premises."""
from __future__ import annotations

import re
from typing import List, Tuple

from .config import DEFAULT_CONFIG
from .dlp import redact
from .models import ExtractedContext, ExtractedPremise, PremiseRegistry, ProvenanceSpan


class PremiseExtractor:
    """Surface likely presuppositions with deterministic confidence scores."""

    _PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
        ("presupposition", re.compile(r"\b(?:since we|given that|as approved by|as agreed|as confirmed|as already established)\b[^.!?;]*", re.I)),
        ("dependency", re.compile(r"\b(?:depends on|dependent on|requires|requires that|needs)\b[^.!?;]*", re.I)),
        ("causality", re.compile(r"\b(?:because|therefore|so that|thus|hence|due to|caused by)\b[^.!?;]*", re.I)),
        ("mutation", re.compile(r"\b(?:change|changed|modify|modified|update|updated|delete|deleted|remove|removed|replace|replaced|increase|decrease|raise|lower|switch|migrate)\b[^.!?;]*", re.I)),
        ("tool_usage", re.compile(r"\b(?:use|using|via|through|with)\s+(?:the\s+)?(?:api|tool|service|database|db|script|system|platform|cli)\b[^.!?;]*", re.I)),
        ("scale", re.compile(r"\b(?:all|every|each|always|never|only|exactly|at least|at most|no more than|no less than)\b[^.!?;]*", re.I)),
        ("declarative", re.compile(r"\b(?:is|are|was|were|has|have|will)\b\s+[^.!?;]*", re.I)),
    )

    _CONFIDENCE = {
        "mutation": lambda c: c.confidence_mutation,
        "tool_usage": lambda c: c.confidence_tool_usage,
        "causality": lambda c: c.confidence_causality,
        "scale": lambda c: c.confidence_scale,
        "declarative": lambda c: c.confidence_declarative_claim,
        "dependency": lambda c: c.confidence_dependency,
        "presupposition": lambda c: 0.50,
    }

    def __init__(self, max_premises: int | None = None) -> None:
        self.config = DEFAULT_CONFIG.premise
        self.max_premises = max_premises if max_premises is not None else self.config.max_premises

    def extract_premises(self, raw_input: str, context: ExtractedContext) -> PremiseRegistry:
        text = raw_input or ""
        candidates: List[Tuple[int, int, str, str]] = []
        seen = set()
        for kind, pattern in self._PATTERNS:
            for match in pattern.finditer(text):
                statement = match.group(0).strip(" \t,;:")
                if not statement:
                    continue
                key = (match.start(), match.end(), statement.lower())
                if key in seen:
                    continue
                seen.add(key)
                candidates.append((match.start(), match.end(), kind, statement))

        # Deterministic order: source position, then pattern priority.
        candidates.sort(key=lambda x: (x[0], x[1], x[2]))
        premises: List[ExtractedPremise] = []
        for start, end, kind, statement in candidates[: self.max_premises]:
            confidence = float(self._CONFIDENCE[kind](self.config))
            requires_verification = confidence < DEFAULT_CONFIG.decoupler.premise_confidence_penalty_threshold
            # Preserve offsets against the unredacted source; redact only the stored text.
            safe_statement = redact(statement)
            premises.append(
                ExtractedPremise(
                    statement=safe_statement,
                    confidence=confidence,
                    provenance=ProvenanceSpan(
                        source_field="raw_input",
                        start_char=start,
                        end_char=end,
                        verbatim_text=redact(text[start:end]),
                    ),
                    requires_verification=requires_verification,
                )
            )
        return PremiseRegistry(premises=premises)
