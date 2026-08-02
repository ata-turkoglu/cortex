# Setup, Secrets, and Cost Controls

## Setup wizard

The wizard validates services, secrets, model assignments, embeddings, GraphRAG automation, budgets, and Windows paths.

## Secret policy

Use an OS-backed secret store where available, with environment-variable fallback for development and Docker. Never store plaintext API keys in SQLite.

## Cost controls

- gpt-5.6-luna defaults
- qwen3-embedding:0.6b multilingual local embeddings
- GraphRAG automatic updates disabled initially
- Batch API for eligible offline jobs
- query expansion disabled by default
- conservative multi-route behavior
- daily/monthly soft budgets
- cost warning and confirmation thresholds
- per-layer and per-workspace usage accounting
