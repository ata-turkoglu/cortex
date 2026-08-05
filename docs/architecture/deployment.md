# Deployment Boundary

Cortex Compose will run frontend, backend, worker, Redis, and Qdrant with exact image
tags. SQLite and runtime data use configurable host mounts. Cortex must not create a second
Ollama container or duplicate KnowledgeOS models; Docker Desktop services use
`OLLAMA_BASE_URL=http://host.docker.internal:11434`, while host processes use localhost.

The production backend targets Python 3.11 on Linux/x86_64 containers. `backend/uv.lock` is
generated inside that Linux runtime with uv 0.12.1; Windows 11 is a host development platform,
not a second GraphRAG lock target. Dependency groups are deliberately split: `query` installs
LlamaIndex for the API route selector; `retrieval` installs BM25S and the local reranker; and
`graphrag` installs Microsoft GraphRAG. Cortex stores GraphRAG vectors through its Qdrant adapter;
LanceDB is not configured as a Cortex runtime vector store.

The frontend container runs package commands from `/app/frontend`; its development command must
therefore not add a second `--dir frontend` path. This keeps the Compose startup path consistent
with the mounted repository layout. The root workspace and `frontend` package each use a named
`node_modules` volume so host-created pnpm symlinks never point to Windows-only paths inside the
Linux container.

Vite proxies browser requests beginning with `/api` to the API service. Host development defaults
to `http://localhost:4000`; Compose sets `VITE_API_PROXY_TARGET=http://backend:8000` so browser
requests served on port 3000 never incorrectly target the Vite port.

The Dockerfile has two build targets. `runtime` is the API image and installs only the `query`
group. `worker` inherits it and installs `retrieval` plus `graphrag`; this is where GraphRAG's
heavy transitive dependencies, including LanceDB, PyArrow, spaCy, Torch, and Graspologic reside.
Microsoft GraphRAG 2.6 declares LanceDB as a direct upstream dependency, so it remains in the
worker image even though Cortex never configures it as a vector store. Build support stays enabled
because some locked transitive packages are source-only distributions.

The API and worker commands run through `uv run --frozen --no-sync` so their executables are
resolved from the image's project virtual environment rather than the system `PATH`; startup
does not modify the frozen dependency environment.
