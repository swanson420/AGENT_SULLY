# scenarios/vendor-renewal — B2B PoV wedge

One vendor, one SKU, one currency. Hard constraints are facts at capture,
not preferences and not inferences.

"Renew Acme Analytics Platform, 50 seats. Current spend is $48,000/year.
Get it to $40,000 or below. Do not accept a term longer than 12 months.
Do not accept auto-renew expansion or a seat-minimum increase."

Three fixture states of the same plant:

- `easy_save` — vendor will accept ≤ $40,000 / ≤ 12 months. Closed save = $8,000.
- `constraint_conflict` — vendor will cut price only if term goes to 24 months. Must not settle.
- `no_give` — vendor floor stays at $48,000. Must not fabricate savings.
