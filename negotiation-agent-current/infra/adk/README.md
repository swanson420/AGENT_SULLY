# infra/adk/ — Google ADK binding

Two ADK agents plus a sequential root. Their tools call `action.close_path`.
Live `Runner` needs `GOOGLE_API_KEY`. Unit tests call the tools directly so
the ledger path does not depend on Gemini being reachable.
