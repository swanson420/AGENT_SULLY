# decision/contracts/ — Shared schema for the triage gate

The current, single source of truth for the triage gate's data shapes. Everything under `decision/triage_gate/` (stages, orchestrator, config) imports from here — nothing defines its own parallel copy of these types.

- `decision_package.py` — `WorkingContext` (source events, raw payload, unknowns, assumptions, commitment level), `DecisionRecord` (route, action, context, blast radius, gate results, audit hash, timestamp, rationale — with `.validate()` enforcing every pre-action gate requirement before a record may reach the ledger), `RouteType`, `ActionType`, `Unknown`, `Assumption`.
- `blast_radius.py` — `BlastRadiusScore` (5 dimensions: reversibility, cost, relationship impact, commitment, external visibility, each an `ImpactLevel` of LOW/MEDIUM/HIGH/CRITICAL), with `.validate()` and `.to_ordinal_map()` for deterministic severity weighting (LOW=1 … CRITICAL=4).

## Why this folder exists separately from `triage_gate/`
An earlier generation of these same concepts (`Route`, `EpistemicTag`, `RecursionMetadata`, a different `BlastRadius`/`Severity` shape) lived directly inside `decision/triage_gate/decision_package.py` and `blast_radius.py`. That generation has been retired — the files were deleted, not migrated — because nothing outside their own closed loop depended on them. `decision/contracts/` is the current and only schema. If you find code importing `decision.triage_gate.decision_package` or `decision.triage_gate.blast_radius` directly, that's a leftover pointing at a generation that no longer exists.

## Contract, not implementation
Nothing in this folder talks to the ledger, computes routes, or runs stages — it only defines the shapes those things pass to each other. `DecisionRecord.validate()` is the one piece of behavior here, and it's deliberately strict: a record that fails validation must never be written to the ledger. An invalid record reaching the ledger is worse than no record — it's a false claim of auditability.
