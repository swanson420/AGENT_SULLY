"""
context_interrogator.py

Stage 1: deterministic extraction of explicitly stated context.  This stage
only extracts literal text; it does not infer intent or validate premises.
"""

from __future__ import annotations

import re
from typing import List

from .config import DEFAULT_CONFIG
from .models import ExtractedContext


class ContextInterrogator:
    """Extract bounded, literal context from raw input and ledger text."""

    _REQ_PATTERN = re.compile(
        r"\b(?:must|required to|need(?:s)? to|needs|requirement(?:s)?(?: are| is)?|should)\b"
        r"\s*(.+?)(?=(?:\s*(?:,|;|\.|\?|!|\bbut\b|\bhowever\b|\bwhile\b|\bwithout\b))|$)",
        re.IGNORECASE,
    )
    _CONSTRAINT_PATTERN = re.compile(
        r"\b(?:cannot|can't|must not|mustn't|without|only|limit(?:ed)? to|cap(?:ped)? at|no more than|not exceed)\b"
        r"\s*(.+?)(?=(?:\s*(?:,|;|\.|\?|!|\bbut\b|\bhowever\b|\bwhile\b|\bwithout\b))|$)",
        re.IGNORECASE,
    )
    _DEPENDENCY_PATTERN = re.compile(
        r"\b(?:depends on|dependent on|requires|uses|via|through|with)\b\s+([^,.;!?]+)",
        re.IGNORECASE,
    )
    _OBJECTIVE_PATTERN = re.compile(
        r"\b(?:want(?:s)?|goal(?: is|:)?|objective(?: is|:)?|trying to|need(?:s)? to)\b\s*([^.;!?]+)",
        re.IGNORECASE,
    )
    _ASSERTION_PATTERN = re.compile(
        r"\b(?:is|are|was|were|has|have|will|currently|already)\b\s+([^.;!?]+)",
        re.IGNORECASE,
    )

    def __init__(self, max_input_chars: int | None = None, max_extracted_items: int | None = None) -> None:
        cfg = DEFAULT_CONFIG.extraction
        self.max_input_chars = max_input_chars if max_input_chars is not None else cfg.max_input_chars
        self.max_extracted_items = max_extracted_items if max_extracted_items is not None else cfg.max_extracted_items

    def extract_context(self, raw_input: str, ledger: str) -> ExtractedContext:
        raw_input = raw_input or ""
        ledger = ledger or ""

        is_truncated = len(raw_input) + len(ledger) > self.max_input_chars
        remaining = self.max_input_chars
        raw = raw_input[:remaining]
        remaining -= len(raw)
        ledger_text = ledger[:max(0, remaining)]

        objectives = self._matches(self._OBJECTIVE_PATTERN, raw)
        requirements = self._matches(self._REQ_PATTERN, raw)
        constraints = self._matches(self._CONSTRAINT_PATTERN, raw)
        dependencies = self._matches(self._DEPENDENCY_PATTERN, raw)

        facts = self._literal_facts(raw)
        if ledger_text.strip():
            facts.extend(f"Ledger baseline: {line.strip()}" for line in ledger_text.splitlines() if line.strip())

        contradictions = self._contradictions(requirements + constraints)

        all_items = objectives + requirements + constraints + facts + dependencies + contradictions
        if len(all_items) > self.max_extracted_items:
            overflow = len(all_items) - self.max_extracted_items
            # Preserve the high-priority fields first and trim the tail.
            facts = facts[: max(0, len(facts) - overflow)]

        return ExtractedContext(
            objectives=objectives,
            requirements=requirements,
            constraints=constraints,
            facts=facts,
            dependencies=dependencies,
            contradictions=contradictions,
            is_truncated=is_truncated,
        )

    @staticmethod
    def _matches(pattern: re.Pattern[str], text: str) -> List[str]:
        return [m.group(1).strip(" \t,;:") for m in pattern.finditer(text) if m.group(1).strip(" \t,;:")]

    @staticmethod
    def _literal_facts(text: str) -> List[str]:
        facts: List[str] = []
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            sentence = sentence.strip()
            if not sentence:
                continue
            if not re.search(r"\b(?:must|required|need|want|goal|objective|cannot|can't|without|only|limit|cap)\b", sentence, re.I):
                facts.append(sentence)
        return facts

    @staticmethod
    def _contradictions(items: List[str]) -> List[str]:
        lower = [item.lower() for item in items]
        contradictions: List[str] = []
        for i, item in enumerate(lower):
            if "must not" in item or "cannot" in item or "can't" in item or "without" in item:
                for j in range(i + 1, len(lower)):
                    if any(token in lower[j] for token in ("must ", "required", "need to", "only ")):
                        contradictions.append(f"{items[i]} | {items[j]}")
        return contradictions
