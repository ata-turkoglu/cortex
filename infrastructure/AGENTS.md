# Infrastructure Context

Read root `AGENTS.md` first. Compose owns frontend, backend, worker, Redis, Qdrant, and the
Query V2 Neo4j service; it must not define an Ollama service. On Docker Desktop, Cortex uses the existing
KnowledgeOS Ollama runtime via `http://host.docker.internal:11434`.

Neo4j uses an exact Community image tag, persistent host data, authentication, and a health check.
Backend/worker startup depends on Neo4j readiness. Never print rendered Compose configuration when
the local `.env` may contain provider or graph credentials; use quiet validation.
