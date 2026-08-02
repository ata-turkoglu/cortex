# Deployment Boundary

Cortex Compose will run frontend, backend, worker, Redis, and Qdrant with exact image
tags. SQLite and runtime data use configurable host mounts. Cortex must not create a second
Ollama container or duplicate KnowledgeOS models; Docker Desktop services use
`OLLAMA_BASE_URL=http://host.docker.internal:11434`, while host processes use localhost.
