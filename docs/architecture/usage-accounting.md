# Usage and cost accounting

`usage_events` is the authoritative, append-only record for one completed provider request. It is
workspace-scoped and can link to a query run, workflow run, and workflow step. The event records
the actual stage, provider/model, provider request ID, provider-normalized token categories,
sanitized provider usage payload, pricing version, decimal cost, and an idempotency key.

Provider-reported counts remain provider-reported; unavailable counts remain null. Local Ollama
calls have zero API charge even when token data is unavailable. A remote call with no matching
rate card remains unpriced/unavailable rather than being treated as free. Query and workflow API
totals are derived from events, so historical runs without events report `recorded: false`.

Rate cards are centralized in `backend/app/accounting.py` as versioned exact provider/model
`RateCard` values. Each newly priced event stores the immutable applied-rate snapshot, selected
version, and computed decimal amount, so later card edits cannot alter history. OpenAI Responses usage is normalized at its adapter boundary; the currently deferred
production Anthropic path and GraphRAG CLI calls remain visible only to the extent their adapters
provide reliable per-call usage.
