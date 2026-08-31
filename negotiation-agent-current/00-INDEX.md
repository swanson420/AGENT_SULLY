# File structure — Negotiation Agent V1

Maps to the V1 spec sections. See `docs/build-plan.md` for the authoritative dependency graph, critical path, and vertical-slice build order — this file is the folder map only.

| Folder | Spec section | Status |
|---|---|---|
| `ledger/` | 1.1 — Immutable Event Ledger (also the audit authority — see `ledger/audit_view.py`) | scaffold |
| `working-context/` | 1.1 — Mutable Working Context | scaffold |
| `interpretation/` | 1.2 — Context Interrogator, Premise Extractor, Goal-vs-Method, Ambiguity Detector, Interpretation Challenge | scaffold |
| `reasoning/control-panel/` | 1.3 — Meta-Gate, OFF/AUTO/FORCE toggles | scaffold |
| `decision/triage-gate/` | 1.4 — 5-step triage skeleton, Decision Package, recursion rule, conflict-resolution rule | scaffold |
| `action/` | 1.5 — Commitment gradient, Action Gate (convergence point after Adversarial Check clears), dispatch | scaffold |
| `adversarial/` | 1.5 — Counterparty Model — a GATE on the Decision Package, not a sibling of `action/`. One return loop into Triage max. | scaffold |
| `feedback/` | 1.6 — Metrics collection (measurement only, no auto-tuning) | scaffold |
| `scenarios/internet-bill/` | Section 2 — MVP scenario definition | scaffold |
| `tests/adversarial/` | Section 3 — Tests 1–6b | scaffold |
| `infra/firestore/` | Ledger + working-context storage backend | scaffold |
| `infra/adk/` | Google ADK / Gemini binding — required stack component | scaffold |
| `docs/` | Architecture diagram, demo script, written description, build-plan.md | scaffold |

## Build order — see docs/build-plan.md

Short version: don't build the Triage Gate fully-featured in isolation. Build a minimal vertical slice — Ledger → WorkingContext/Interpretation → Triage → Action → Audit event → Ledger — on one trivial path, prove Test 1, then add Test 2, 3, 6b, 5, 4 in that order as branches. Meta-Gate AUTO logic, Firestore, and ADK binding all wait until M0 (all six tests + governance invariants) is green.
