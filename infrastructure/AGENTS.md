# Infrastructure Context

Read root `AGENTS.md` first. Compose owns Cortex infrastructure only: Redis, Qdrant, Query V2
Neo4j, Ollama, and the one-shot `ollama-models` bootstrap. Frontend, backend, and worker run on
the host and use `http://127.0.0.1:11434` for Cortex-owned Ollama. Do not reference KnowledgeOS
Compose files or volumes at runtime. `ollama-models` must remain idempotent and provision only the
explicit Cortex model list.

Neo4j uses an exact Community image tag, persistent host data, authentication, and a health check.
Backend/worker startup depends on Neo4j readiness. Never print rendered Compose configuration when
the local `.env` may contain provider or graph credentials; use quiet validation.
