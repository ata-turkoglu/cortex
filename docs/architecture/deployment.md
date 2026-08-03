# Deployment Boundary

Cortex Compose will run frontend, backend, worker, Redis, and Qdrant with exact image
tags. SQLite and runtime data use configurable host mounts. Cortex must not create a second
Ollama container or duplicate KnowledgeOS models; Docker Desktop services use
`OLLAMA_BASE_URL=http://host.docker.internal:11434`, while host processes use localhost.

The production backend targets Python 3.11 on Linux/x86_64 containers. `backend/uv.lock` is
generated inside that Linux runtime with uv 0.12.1; Windows 11 is a host development platform,
not a second GraphRAG lock target. The `graphrag` dependency group installs Microsoft GraphRAG,
LlamaIndex, BM25S, and the local reranker dependencies. Cortex stores GraphRAG vectors through
its Qdrant adapter; LanceDB is not configured as a Cortex runtime vector store.
