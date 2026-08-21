# Deployment Boundary

Cortex Compose runs frontend, backend, worker, Redis, Qdrant, and Neo4j with exact image
tags. SQLite and runtime data use configurable host mounts. Cortex must not create a second
Ollama container or duplicate KnowledgeOS models; Docker Desktop services use
`OLLAMA_BASE_URL=http://host.docker.internal:11434`, while host processes use localhost.

Query V2 pins Neo4j Community `2026.07.1` and the official Python driver `6.2.0`. Neo4j persists
under `data/neo4j`, publishes Browser HTTP on 7474 and Bolt on 7687, and exposes an authenticated
`cypher-shell` health check. Backend and worker connect over `bolt://neo4j:7687`; the password comes
from `CORTEX_NEO4J_PASSWORD` or the encrypted Cortex secret store and is never persisted in global
settings. The checked-in Compose fallback is local-development only and must be overridden outside
that environment. Neo4j Community Edition is GPLv3; distribution review remains mandatory.

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

Runtime containers use `TZ=Europe/Istanbul` for local operational timestamps. Persistent API
timestamps remain UTC and the frontend explicitly formats them for the Istanbul time zone.

For no-build host development, Redis, Qdrant, and Neo4j are published on `localhost:6379`,
`localhost:6333`, and `localhost:7687`. Set the host backend's Neo4j URI to
`bolt://localhost:7687` and `VITE_API_PROXY_TARGET=http://host.docker.internal:4000`, recreate the
frontend/Redis/Qdrant/Neo4j Compose services, then run backend and worker from `backend/.venv` with
the same mounted `data` directory. The normal Compose default remains `http://backend:8000`.

The Dockerfile has two build targets. `runtime` is the API image and installs only the `query`
group. `worker` inherits it and installs `retrieval` plus `graphrag`; this is where GraphRAG's
heavy transitive dependencies, including LanceDB, PyArrow, spaCy, Torch, and Graspologic reside.
Microsoft GraphRAG 2.6 declares LanceDB as a direct upstream dependency, so it remains in the
worker image even though Cortex never configures it as a vector store. Build support stays enabled
because some locked transitive packages are source-only distributions.

The API command first runs `alembic upgrade head`, then starts through `uv run --frozen --no-sync`
so its executables are resolved from the image's project virtual environment rather than the system
`PATH`. This applies schema migrations before the API accepts requests without modifying the frozen
dependency environment.

Provider credentials can be supplied non-interactively from `infrastructure/.env` through the
`CORTEX_OPENAI_API_KEY` and `CORTEX_ANTHROPIC_API_KEY` Compose variables. For interactive Docker
use, the settings UI stores credentials encrypted in the mounted `/data/secrets` fallback store
when no OS keyring is available. The fallback is outside SQLite, survives container recreation,
and never returns secrets to the frontend.

## Python image build and runtime-data boundary

`backend/Dockerfile` builds the `runtime` (API) and `worker` targets through clean multi-stage
builds. `query-deps` installs the common API dependency group from the locked manifests before
application code is copied. The worker extends that cached dependency stage with `retrieval` and
`graphrag`; each final target copies only its completed virtual environment, application source,
and Alembic migrations. Consequently, neither target inherits a prior `uv sync` layer or package
manager cache. Builder-stage `uv sync` commands share a BuildKit cache mount. Large
PyTorch/NVIDIA wheels download serially with a 1,800-second uv timeout and five retries; completed
downloads remain available to later normal cached build attempts without entering a final image.

The root `.dockerignore` is an allowlist for the files required by those targets. It excludes local
virtual environments, test/cache/build output, configuration secrets, frontend files, and all
persistent runtime data. Compose continues to mount runtime state at `/data` and sets
`CORTEX_DATA_PATH=/data` for both the API and worker; SQLite, uploaded files, normalized
documents, GraphRAG artifacts, and Qdrant storage are never copied into an image.

The current Linux/x86_64 lock resolves CUDA/NVIDIA packages through PyTorch, which is required by
Docling as well as the local BGE reranker. Cortex does not configure GPU execution, but switching
to a CPU-only PyTorch distribution would require a separately validated lock resolution that is
compatible with those upstream packages. It is intentionally not forced by this image refactor.
Heavy worker-only GraphRAG dependencies (including LanceDB, PyArrow, spaCy, Torch, and
Graspologic) remain necessary for the current Microsoft GraphRAG dependency group.
