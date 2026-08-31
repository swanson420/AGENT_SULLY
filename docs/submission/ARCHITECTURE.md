# Architecture — vendor-renewal close path

Nothing acts until it is an event on a hash-chained ledger. The plant cannot invent a concession. Settlement cannot record savings that violate the baseline cap.

```mermaid
flowchart TD
  B[baseline event] --> C[classify_commitment_level]
  C -->|level less than 3| O[offer event]
  C -->|level 3 or more| A[human_ack event]
  A --> O
  O --> M[offer_sent sandbox mailbox]
  M --> P[sandbox vendor plant]
  P --> R[counterparty_reply]
  R -->|ACCEPT and constraints hold| S[settlement + savings]
  R -->|COUNTER REJECT or constraint miss| H[halt human_required]
  S --> X[export pack + metrics scan]
  H --> X
```

ADK wrap (optional Runner; tools are the source of money figures):

```mermaid
flowchart LR
  Root[SequentialAgent negotiation_root]
  Root --> Closer[LlmAgent vendor_closer]
  Root --> Witness[LlmAgent witnessed_closer]
  Closer -->|run_vendor_close| Path[close_path]
  Witness -->|run_witnessed_close| WPath[witnessed_close_path]
  Path --> Ledger[hash-chained ledger]
  WPath --> Ledger
```
