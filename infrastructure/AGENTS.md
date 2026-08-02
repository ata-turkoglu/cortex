# Infrastructure Context

Read root `AGENTS.md` first. Compose will own frontend, backend, worker, Redis, and
Qdrant; it must not define an Ollama service. On Docker Desktop, Cortex uses the existing
KnowledgeOS Ollama runtime via `http://host.docker.internal:11434`.
