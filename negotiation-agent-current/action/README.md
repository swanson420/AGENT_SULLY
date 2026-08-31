# action/ — Commitment gradient + Action Gate + dispatch

`action_gate.py` is the convergence point after a Decision Package has cleared (or looped once through) the Adversarial Check — see `decision/triage_gate/README.md`. This is where commitment-level classification (0–5) and dispatch actually happen; nothing dispatches before passing through this gate.

Levels 0–5 (informational → material/irreversible). Higher level → stronger gating, independent of what blast-radius alone concluded.

Every pass through the gate produces an audit event written to the ledger (see `ledger/README.md`) — not a separate audit database.

Dispatch targets: research, draft, send, wait, bounce.
