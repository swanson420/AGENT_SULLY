# interpretation/ — Context Interrogator, Premise Extractor, Goal vs. Method, Ambiguity Detector, Interpretation Challenge

Runs against incoming input before any decision gets made. Writes to working-context, reads from ledger.

## Already built — scaffolding, orchestration, schema, and support (do not re-ask for these)
- `base.py` — Protocol definitions for all 5 stages below. Any stage implementation must satisfy its protocol here.
- `models.py` — Pydantic schema: `ExtractedContext`, `ExtractedPremise`/`PremiseRegistry`, `IntentDecoupling`, `AmbiguityItem`/`AmbiguityReport`, `InterpretationChallenge`, `StageAttestation`, `WorkingContext`, `EpistemicRecord`, `EpistemicTag`.
- `engine.py` — Deterministic pipeline orchestrator. `execute()` runs all 5 stages and returns full state + a `PolicyGateReport` for introspection. `commit()` is the real production entrypoint and always honors the policy gate's verdict. `execute_and_serialize()` exists for backward compatibility only and explicitly bypasses the gate.
- `config.py` — `PipelineSystemConfig` (frozen, per-stage thresholds: confidence weights, risk weights, max-item caps).
- `dlp.py` — Bounded redaction pre-filter (connection strings, bearer tokens, API keys, high-entropy tokens) applied before raw text reaches a `ProvenanceSpan`, a decoupled method vector, or a serialized epistemic record. Not a full PII/DLP engine by design.
- `policy_gate.py` — Evaluates a `WorkingContext` against halt conditions (degraded execution, unresolved blocking ambiguity, risk-score breach) and produces a verdict. Decides only — `engine.py.commit()` is what actually withholds output.
- `serializer.py` — `WorkingContextSerializer`, the boundary adapter into `working-context/`. Maps typed pipeline output into ordered `[F][I][A][U][Q]` records, losslessly.

## Still needed — the 5 stage implementations
Each file below is empty. Each one implements the matching Protocol already defined in `base.py`, and gets composed automatically by the already-built `engine.py` — no new wiring required, just the stage logic itself.

- `context_interrogator.py` (`ContextInterrogatorStage`) — objective, requirements, constraints, facts, inferences, assumptions, ambiguities, contradictions, dependencies.
- `premise_extractor.py` (`PremiseExtractorStage`) — surfaces hidden premises for checking, not silent acceptance.
- `goal_vs_method.py` (`GoalVsMethodStage`) — separates what the user wants from the method they proposed.
- `ambiguity_detector.py` (`AmbiguityDetectorStage`)
- `interpretation_challenge.py` (`InterpretationChallengeStage`) — "what's the strongest plausible interpretation under which my planned action would be wrong?"

See `TRACE.md` for the full red-team flag history (57 tracked) against this subsystem.
