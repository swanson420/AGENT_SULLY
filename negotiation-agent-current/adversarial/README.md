# adversarial/ — Counterparty Model — a GATE on the decision, not a sibling of action/

Corrected in Claude #32 / build-plan.md: this module does not run in parallel with `action/` and feed into a shared downstream step. It sits between Triage's Decision Package and the Action Gate, with the authority to bounce the package back into Triage once.

Why this matters concretely: without this correction, an action could be dispatched and adversarial analysis could run concurrently, discovering a problem (e.g. "this wording reveals our walk-away price") only after the send — after reversibility was already spent. The gate placement prevents that.

Models: what the counterparty wants, knows, is likely to infer, their incentives, how our message could be used against us, which response worsens vs. protects our position.

Triggered contextually (pressure tactics, inconsistent numbers, deadline claims in incoming messages) — logged as its own toggle event.

One return loop into Triage maximum. A second objection on the same package escalates to a human bounce (domain uncertainty), it does not loop again.
