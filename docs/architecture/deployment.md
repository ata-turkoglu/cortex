# Deployment Boundary

Cortex Compose owns infrastructure only: Redis, Qdrant, Neo4j, Ollama, and the one-shot
`ollama-models` bootstrap, all with exact image references. Frontend, backend, and worker run on
the host. Cortex Ollama publishes only `127.0.0.1:11434`, stores models in the named
`cortex_ollama_models` volume, and is reached by both host backend and host worker through
`CORTEX_OLLAMA_BASE_URL=http://127.0.0.1:11434`. It has no runtime dependency on KnowledgeOS.
`ollama-models` waits for Ollama health, checks `CORTEX_OLLAMA_REQUIRED_MODELS`, and pulls only
missing models; the persisted configured embedding model is currently `bge-m3:latest`.

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

Vite proxies browser requests beginning with `/api` to the host API. Host development defaults to
`http://localhost:4000`; configure `VITE_API_PROXY_TARGET=http://127.0.0.1:4000` when needed so
browser requests served on port 3000 never incorrectly target the Vite port.

Runtime containers use `TZ=Europe/Istanbul` for local operational timestamps. Persistent API
timestamps remain UTC and the frontend explicitly formats them for the Istanbul time zone.

For host development, Compose publishes Redis, Qdrant, Neo4j, and Ollama on
`localhost:6379`, `localhost:6333`, `localhost:7687`, and `127.0.0.1:11434`. Set the host
backend and worker URIs to `redis://localhost:6379/0`, `http://localhost:6333`,
`bolt://localhost:7687`, and `http://127.0.0.1:11434`; run frontend, backend, and worker from
their host development environments with the same `data` directory.

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
