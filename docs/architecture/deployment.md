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
persistent runtime data. Compose continues to mount runtime state at `/data`; SQLite, uploaded
files, normalized documents, GraphRAG artifacts, and Qdrant storage are never copied into an
image.

The current Linux/x86_64 lock resolves CUDA/NVIDIA packages through PyTorch, which is required by
Docling as well as the local BGE reranker. Cortex does not configure GPU execution, but switching
to a CPU-only PyTorch distribution would require a separately validated lock resolution that is
compatible with those upstream packages. It is intentionally not forced by this image refactor.
Heavy worker-only GraphRAG dependencies (including LanceDB, PyArrow, spaCy, Torch, and
Graspologic) remain necessary for the current Microsoft GraphRAG dependency group.
