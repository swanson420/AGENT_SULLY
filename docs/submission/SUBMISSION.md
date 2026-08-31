# Negotiation agent — vendor-renewal PoV

Governed close of one B2B SaaS renewal. Every dollar on the pack is computed from ledger events. The model is not allowed to invent savings.

## What a reviewer can replay

From repo root:

```bash
PYTHONPATH=. python -m pytest tests/test_pov_vendor_renewal_e2e.py -q
PYTHONPATH=. python -m action.close_path easy_save
PYTHONPATH=. python -m action.close_path --witnessed easy_save
```

Packs in this folder:

| File | Path | Terminal | Savings |
|---|---|---|---|
| `demo-easy_save.json` | ACCEPT $40k / 12 | settlement | $8,000 |
| `demo-constraint_conflict.json` | COUNTER $38k / 24 | halt | $0 |
| `demo-no_give.json` | REJECT | halt | $0 |
| `demo-witnessed-easy-save.json` | MUTATE_STATE + human_ack | settlement | $8,000 |

Easy-save chain:

`baseline → offer → offer_sent → counterparty_reply → settlement`

Witnessed chain adds `human_ack` after baseline because `classify_commitment_level(MUTATE_STATE)` is 5.

## Structured disclosures (do not soften)

- `adversarial_check_scope`: `synthetic_offer_text` — assess ran on `Offer 40000 USD for 12 months.`, not the vendor email.
- `commitment_trigger`: `none` on default easy-save (EXECUTE_QUERY, all MEDIUM, level 2). `mandatory_escalation` on the witnessed pack (MUTATE_STATE, level 5). That is the top of the scale, not the ≥3 blast boundary.
- ADK: `infra/adk/agent_binding.py` defines real `LlmAgent` / `SequentialAgent` objects whose tools call `close_path`. **Gemini was never invoked in this environment.** There was no API key. Do not write “Gemini generated the offer.”
- Mailbox is `sandbox_log` + an `offer_sent` event. Not SMTP.

## Freeze that held

No Firestore. No live inbox. No counterparty-email assess (known two-`$` false positive). No LLM-authored savings.

## Stack

Python control loop + hash-chained in-memory ledger + Google ADK agent graph wrapping that loop. Required for the loop: `pydantic`. Required for the ADK objects: `google-adk`.
