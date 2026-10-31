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

## Recorded stages

| Stage | Recorded by | Link |
| --- | --- | --- |
| `semantic_planner` | `app/query/production_chat.py`, in the same short transaction that persists the answer or the failure | `query_run_id`; one event per billed attempt, including repaired and failed attempts |
| `knowledge_extraction` | `app/knowledge/production_executor.py`, in a separate short transaction after each extraction batch (also when the batch fails) | workspace and generation (via the idempotency key) |
| `answer_synthesis` | `app/query/production_chat.py`, with the answer | `query_run_id`; one event per synthesis attempt |
| `graphrag_search` | `app/query/production_chat.py`, from the GraphRAG engine trace counters | `query_run_id`; token counts estimated by GraphRAG's tokenizer |
| `conversation_summary` | `app/query/conversation_summary.py`, in the short transaction that stores the summary | conversation workspace |

Accounting failures during extraction are logged and never discard checkpointed extraction work.
GraphRAG CLI indexing calls are not recorded because the upstream CLI does not report per-call
usage.

## Soft budgets

`GET /settings/budgets` reports today's and this month's priced spend (UTC periods, all
workspaces) against `daily_soft_budget_usd` and `monthly_soft_budget_usd`, with a state of `ok`,
`warning` (at `budget_warning_percent`), `exceeded`, or `unbounded` (budget `0`), plus the count of
calls without a known price. Enforcement is `warn_only`: budgets never pause or block work.
