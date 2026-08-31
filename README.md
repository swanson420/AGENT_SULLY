# Negotiation Agent (V1)

An agent architecture for negotiation tasks built around one rule: nothing acts until it has passed through an auditable chain of gates. Every claim is traceable back to an immutable event ledger, every decision carries an explicit blast-radius and commitment-level assessment, and every irreversible action clears an adversarial (counterparty-modeling) check before it's allowed to dispatch.

Stack: Gemini + Google ADK (Agent Development Kit) + Google Cloud, per the target hackathon rules. See `docs/build-plan.md` for why.

## Architecture

```
LEDGER (immutable, hash-chained)
   │
   ├──► WORKING CONTEXT ──┐
   └──► INTERPRETATION ───┴──► META-GATE ──► TRIAGE GATE ──► DECISION PACKAGE
                                                                     │
                                                     ┌───────────────┴───────────────┐
                                                     ▼                               ▼
                                              ADVERSARIAL CHECK               (clears straight)
                                              (may bounce back to
                                               TRIAGE, max 1 loop)
                                                     └───────────────┬───────────────┘
                                                                     ▼
                                                               ACTION GATE
                                                                     │
                                                        ┌────────────┴────────────┐
                                                        ▼                         ▼
                                                  ACT / BOUNCE              AUDIT EVENT
                                                        └────────────┬────────────┘
                                                                     ▼
                                                                  LEDGER
```

Full dependency graph, build order, and rationale for each correction to this design: [`docs/build-plan.md`](docs/build-plan.md).

## Module map

| Module | Responsibility |
|---|---|
| `ledger/` | Append-only, hash-chained event log. The single source of truth for "what happened." `audit_view.py` reads audit data as a *view* over ledger entries — there is no separate audit store. |
| `working-context/` | Mutable current beliefs (interpretation, objective, facts, assumptions, unknowns) derived from the ledger. Every claim carries an epistemic tag (`[F]` fact, `[I]` inference, `[A]` assumption, `[U]` uncertain, `[Q]` open question). |
| `interpretation/` | Runs on incoming input before any decision: Context Interrogator, Premise Extractor, Goal-vs-Method, Ambiguity Detector, Interpretation Challenge. Pydantic schemas in `models.py`, orchestrator in `engine.py`. |
| `reasoning/` | Meta-Gate: OFF / AUTO / FORCE control over how much reasoning runs. |
| `decision/` | `triage_gate/` — the core 5-step triage loop (unknown surfacing → resolvability → blast-radius → routing → decision package). `contracts/` — the shared schema (`DecisionRecord`, `BlastRadiusScore`, etc.) everything else imports. |
| `adversarial/` | Counterparty Model. A **gate** on the Decision Package (not a parallel branch to `action/`) — sits between Triage output and the Action Gate, with authority to bounce the package back into Triage once. |
| `action/` | Commitment-gradient classification (0–5), Action Gate (the convergence point after Adversarial clears), and dispatch. Every pass writes an audit event to the ledger. |
| `feedback/` | Metrics collection only — clarifications requested, overrides, uncertainty events, outcomes. No automatic self-tuning; review is manual. |
| `scenarios/internet-bill/` | The MVP negotiation scenario used to drive and validate the pipeline end to end. |
| `infra/firestore/` | Firestore-backed persistence for the ledger and working context. Stubbed — bound after core logic is proven against an in-memory store. |
| `infra/adk/` | Google ADK / Gemini binding. Deferred until the core pipeline passes its tests against the in-memory stub. |
| `tests/` | Test suite, organized by module (see `tests/decision/triage_gate/` for the most complete coverage so far). |
| `docs/` | Build plan, architecture decision records (`docs/architecture/decisions/`), and submission materials. |

See `00-INDEX.md` for the folder-to-spec-section mapping and current build status of each module.

## Design invariants

These hold across every module and are the main thing a change should not violate:

1. **The ledger is the only authority.** Working context, audit views, and decision records are all derived from it — never a second source of truth for "what happened."
2. **Claims are traceable.** Anything the agent treats as a fact must trace back to a ledger entry; inferences and assumptions are tagged as such and never silently promoted to fact.
3. **Adversarial check is a gate, not a parallel path.** It sits between the Decision Package and the Action Gate, with at most one bounce back into Triage — so a risky action can never dispatch while adversarial analysis is still running concurrently.
4. **Commitment level gates independently of blast radius.** Higher commitment (0–5) means stronger gating even if blast-radius alone looked mild.
5. **No silent auto-tuning.** `feedback/` measures; policy changes are manual, reviewed, and retested.

## Getting started

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

Run the test suite:

```bash
pytest
```

Firestore and ADK bindings (`infra/firestore/`, `infra/adk/`) are intentionally not wired up yet — the build plan requires proving the pipeline against an in-memory stub first (see `docs/build-plan.md`, "M0 gate").

## Status

Scaffold stage — module boundaries, schemas, and orchestration are in place; see `00-INDEX.md` for a per-folder status table and `docs/build-plan.md` for the current point on the build order (vertical slice → branches → M0 gate → ADK/Firestore/demo).

## License

MIT — see [`LICENSE`](LICENSE).
