# Cortex — Master Implementation Prompt for Codex

You are building a new project named **Cortex**.

Cortex is a local, single-user, workspace-based knowledge platform for uploading documents, indexing them, querying them through hybrid retrieval and Microsoft GraphRAG, and observing all background workflows through a visual process map.

This is a new system. Do not reuse or depend on the old KnowledgeOS project.

---

## Mandatory execution behavior

- Read this file first.
- Then read `docs/DECISIONS.md`.
- Execute the files under `phases/` in numeric order.
- Maintain `IMPLEMENTATION_STATUS.md`.
- Replace `[ ]` with `[x]` only after the corresponding task is fully implemented and validated.
- Mark every fully implemented and validated task as `[x]` in its owning file under `phases/` before reporting the work complete.
- When a task is partially complete, leave it unchecked and add a short indented note explaining what remains.
- Do not silently change architectural decisions.
- If a required library API differs from expectations, adapt the implementation while preserving the architecture and document the deviation.
- Do not scan the entire repository before each task.
- Follow the AI context navigation system created in Phase 1.
- Keep generated files, uploaded data, model files, indexes, caches, build artifacts, and dependencies out of AI context unless the current task explicitly concerns them.
- Run relevant tests, type checks, migrations, and health checks before marking a phase complete.
- At the end of every phase:
  - update `IMPLEMENTATION_STATUS.md`,
  - summarize changed files,
  - list validation commands and results,
  - list unresolved issues,
  - update architecture/context documentation if public interfaces, workflows, schemas, module responsibilities, or folder structures changed.

---

## Final technology stack

### Frontend

- React
- Vite
- TypeScript
- Tailwind CSS
- PrimeReact
- lucide-react
- React Router
- Zustand
- TanStack Query
- React Hook Form
- Zod
- React Flow

### Backend

- Python
- FastAPI
- Pydantic v2
- SQLAlchemy 2
- Alembic
- SQLite
- LlamaIndex
- LlamaIndex Workflows
- Docling
- Qdrant
- bm25s
- Microsoft GraphRAG
- NetworkX
- local BGE reranker
- Dramatiq
- Redis
- Server-Sent Events
- structured JSON logging

### LLM providers

- Ollama
- OpenAI
- Anthropic

### Embedding providers

- Ollama
- OpenAI

### Deployment

- Docker Compose
- Services:
  - frontend
  - backend
  - worker
  - redis
  - qdrant
- Ollama is provided by the existing KnowledgeOS Docker stack and must not be
  duplicated by Cortex.
- The local layout is `D:\Merter\KnowledgeOS` for KnowledgeOS and
  `D:\Merter\Cortex` for Cortex. Start KnowledgeOS from its repository with
  `docker compose up -d`.
- KnowledgeOS publishes Ollama on host port `11434` and stores the models in
  its existing `ollama-data` volume.
- When Cortex runs inside Docker Desktop on Windows, use
  `OLLAMA_BASE_URL=http://host.docker.internal:11434` for the backend and
  worker. When Cortex runs on the host, use
  `OLLAMA_BASE_URL=http://localhost:11434`.
- Add `extra_hosts: ["host.docker.internal:host-gateway"]` to Cortex services
  when Docker compatibility requires it.
- Do not add an Ollama service to Cortex Compose, pull models during startup,
  or mount/copy the KnowledgeOS `ollama-data` volume into another container.
- If both projects are later combined into one Compose project, keep one
  Ollama service and use `OLLAMA_BASE_URL=http://ollama:11434`.

---

## Core product rules

- Global settings only in V1.
- No workspace setting overrides in V1.
- Every workspace acts as an isolated knowledge application.
- All relational data is stored in one SQLite database.
- Every workspace-scoped relational table uses `workspace_id`.
- Qdrant collections are shared by resource type and isolated through required `workspace_id` payload filters.
- Qdrant collection/resource mappings are stored in the database.
- `WorkspaceContext` resolves all workspace resources.
- Microsoft GraphRAG is an independent query engine integrated into LlamaIndex through adapters/query-engine tools.
- GraphRAG Local, Global, and DRIFT remain distinct query paths.
- LlamaIndex Router chooses Hybrid Search, GraphRAG Local, GraphRAG Global, GraphRAG DRIFT, or approved multi-route combinations.
- Hybrid Search uses Qdrant dense retrieval, bm25s sparse retrieval, fusion, and a local BGE reranker.
- NetworkX is a secondary graph representation for visualization and traversal.
- The Microsoft GraphRAG knowledge model remains canonical for graph data.
- Cortex chunks and GraphRAG text units are separate in V1.
- Background jobs persist across page changes and application navigation.
- Workflow state is persisted in SQLite.
- Dramatiq and Redis execute background jobs.
- REST is used for commands.
- SSE is used for live progress updates.
- React Flow visualizes both static system architecture and live workflow runs.
- User-visible errors show a concise summary first.
- A “Show technical details” action reveals sanitized traceback and technical metadata.
- Backup/restore is not part of V1.
- Index updates overwrite the active index in place.
- Temporary staging may be used internally to prevent partial corruption.

---

## Frontend abstraction rules

PrimeReact, lucide-react, and React Flow are replaceable implementation details.

Feature code must use Cortex-owned abstractions.

Required components include at minimum:

- `AButton`
- `ADialog`
- `ATable`
- `AInput`
- `ASelect`
- `ATextarea`
- `ACheckbox`
- `ARadio`
- `ASwitch`
- `ATabs`
- `ATooltip`
- `AToast`
- `AMenu`
- `AFileUpload`
- `ATree`
- `ACard`
- `ABadge`
- `AProgress`
- `ASkeleton`
- `AConfirmDialog`
- `APaginator`
- `ADatePicker`
- `ADrawer`
- `ASplitPanel`
- `AInfo`
- `AIcon`
- `APlatformLayout`
- `ASidebar`
- `AHeader`
- `APageContent`
- `AGlobalProgress`
- `AFlowCanvas`
- `AWorkflowDialog`
- `ASystemMap`

Rules:

- No direct PrimeReact imports outside the approved UI adapter/component layer.
- No direct lucide-react imports outside the icon registry or `AIcon` implementation.
- No direct React Flow business coupling outside the flow abstraction layer.
- `AInfo` is used where explanation, side effects, warnings, or technical meaning need clarification.
- `AIcon` supports icon-only rendering and icon plus tooltip.
- All public abstraction components have typed Cortex-owned props.
- PrimeReact-specific event types must not leak into feature code.

---

## Platform layout

The application shell is:

```text
Sidebar + (Header + Content)
```

Requirements:

- Sidebar is collapsed by default.
- Collapsed sidebar shows navigation icons only.
- Icon labels are available through tooltips.
- A button on the left side of the header expands or collapses the sidebar.
- On narrow screens, the sidebar behaves as a drawer.
- Header contains page title/breadcrumb, background job progress, active-job indicator, and system health.
- Background activity appears as a loading/progress bar in the header.
- Clicking the background activity area opens active process details.

---

## Settings rules

Global Settings must include:

- Appearance:
  - light/dark/system
  - PrimeReact theme preset
  - primary color
  - surface palette
  - border radius
  - UI density
  - font scale
  - animations
- Provider connections:
  - Ollama
  - OpenAI
  - Anthropic
- Layer-specific model assignments
- Embedding provider/model
- Operational thresholds
- Retrieval top-k values
- Reranker top-k
- Router thresholds
- GraphRAG pending-document trigger threshold
- Stage concurrency limits
- Retry and timeout settings
- Retention settings
- Health-check interval
- SSE reconnect interval
- Batch sizes
- Conversation memory limits
- Answer style and grounding rules

Thresholds must not be hard-coded if they are operationally tunable.

---

## AI coding context system

Create a vendor-neutral AI development context system.

Canonical instructions:

- root `AGENTS.md`
- scoped nested `AGENTS.md`
- `docs/ai/index.md`
- `.ai/project-map.yaml`

Thin adapters:

- `CLAUDE.md`
- `GEMINI.md`

Automation:

- `scripts/ai-context/generate-adapters.py`
- `scripts/ai-context/validate-context.py`
- `scripts/ai-context/check-context-freshness.py`

The AI context system must reduce unnecessary repository scanning and must route tools to only the files relevant to a task.

---

## Completion definition

The project is complete only when:

- all phase checklists are checked,
- all required services run through Docker Compose,
- database migrations apply cleanly,
- frontend type checking passes,
- backend tests pass,
- critical integration tests pass,
- workspace isolation is verified,
- no Qdrant search can execute without a workspace filter,
- background workflows survive page navigation,
- SSE reconnect restores current state,
- React Flow shows live workflow progress,
- Settings values drive the relevant runtime behavior,
- technical trace details are available on demand and sanitized,
- all AI context documents validate,
- `IMPLEMENTATION_STATUS.md` shows no unresolved blocking items.

## Additional mandatory architecture and delivery rules

### Dependency pinning

- Pin all Python and JavaScript dependencies to exact versions.
- Pin Docker image tags to exact versions.
- Do not use floating tags such as `latest`.
- Store the versions used for each index run where relevant.
- Add upgrade notes and compatibility checks for LlamaIndex, Microsoft GraphRAG, Docling, Qdrant, bm25s, Dramatiq, Redis, FastAPI, PrimeReact, React Flow, and the local BGE reranker.
- Add a dependency update procedure that runs tests and evaluation fixtures before accepting upgrades.

### V1 page inventory

The V1 frontend must include routes/pages for:

- Dashboard
- Workspaces
- Workspace overview
- Documents
- Document details and versions
- Upload/import
- Chat
- Conversations
- Processes
- Failed jobs and diagnostics
- Graph explorer
- System map
- Settings
- Provider/model settings
- Appearance settings
- Health/status

### API contract

- Define all REST/SSE request and response models with Pydantic.
- Use a consistent error envelope:
  - `code`
  - `message`
  - `correlation_id`
  - `details_available`
  - optional sanitized `details`
- Expose OpenAPI from FastAPI.
- Generate the frontend TypeScript API client and types from OpenAPI.
- Feature code must use the generated API client rather than duplicating API types manually.
- Treat the OpenAPI schema as a tested contract.

### SQLite concurrency policy

SQLite must be configured for backend and worker concurrency:

- WAL mode
- foreign keys enabled
- busy timeout
- short transactions
- bounded retry for lock contention
- no long-running network/model calls inside open database transactions
- migrations and tests must verify these settings

### Upload and file-security policy

Implement:

- configurable maximum file size
- allowed-extension validation
- MIME/content-type validation
- filename normalization
- path traversal prevention
- unique storage naming
- safe handling of corrupt files
- safe handling of encrypted/password-protected files
- archive-bomb prevention if archive support is added later
- rejection of unsupported formats with a structured error
- checksums before processing
- no execution of uploaded content

### GraphRAG–Qdrant adapter

The Microsoft GraphRAG to Qdrant integration is a first-class technical risk and must be isolated:

- create a dedicated adapter module
- define explicit interfaces and schemas
- include integration tests
- verify workspace isolation
- verify entity/report/text-unit vector separation
- verify Local, Global, and DRIFT query behavior
- document any limitations or deviations from upstream GraphRAG APIs

### Performance targets

Design and validate for approximately 5,000 files.

Requirements:

- large document tables use server-side pagination
- long lists use virtualization where appropriate
- React UI remains responsive during background processing
- batch sizes are configurable
- ingestion concurrency is configurable
- retrieval limits are configurable
- performance benchmarks record:
  - ingestion throughput
  - query latency
  - GraphRAG update duration
  - memory usage
  - Qdrant size
  - SQLite size
- define realistic baseline targets in documentation and capture measured results

### External source-file behavior

V1 does not watch arbitrary external folders for file changes.

- Files enter Cortex through supported upload/update flows.
- External edits are not automatically detected.
- Re-uploading or replacing a file triggers hash/version logic.
- File watching is a future feature.

### Startup recovery and graceful shutdown

- On shutdown, workers should stop accepting new work and finish or safely checkpoint atomic steps.
- On startup, stale `running` jobs must be detected.
- Stale jobs become `interrupted` or resume from a safe checkpoint according to workflow rules.
- Recovery actions must be visible in the process UI.
- Do not leave jobs permanently marked `running` after a crash or restart.

### Deletion and orphan reconciliation

- Document and workspace deletion must be implemented as idempotent workflows.
- Reconcile SQLite, Qdrant, bm25s, GraphRAG files, NetworkX outputs, uploads, normalized files, and caches.
- If cleanup partially fails, create a repair/reconciliation job.
- Add a periodic orphan-reconciliation task.
- Never silently leave cross-store orphan data.

### License compliance

- Create `THIRD_PARTY_NOTICES.md`.
- Record major third-party dependencies and licenses.
- Add an automated dependency-license check where practical.
- Document any license restrictions that affect distribution.

## Default model profile for the target machine

The target machine is a Windows laptop with approximately:

- Intel i7-9750H
- 16 GB RAM
- NVIDIA GTX 1650
- limited SSD capacity
- Ollama available, but `qwen3:4b` does not perform well enough for reliable Cortex production tasks
- an OpenAI API key is available

Therefore:

- Do not assign an Ollama chat model as a production default.
- Ollama remains optional for experimentation, offline fallback, and user-selected low-risk tasks.
- Do not automatically download or delete Ollama models.
- List installed Ollama models and show the exact `ollama pull ...` command for missing optional models.
- Never block initial setup because no Ollama chat model is installed.

### Cost-controlled OpenAI defaults

Use these default assignments, while keeping every assignment configurable:

| Cortex layer                  | Default provider | Default model             | Notes                                                  |
| ----------------------------- | ---------------- | ------------------------- | ------------------------------------------------------ |
| Query Router                  | OpenAI           | `gpt-5.6-luna`            | Low-cost classification/routing with structured output |
| Metadata Extraction           | OpenAI           | `gpt-5.6-luna`            | Batchable structured extraction                        |
| Conversation Summary          | OpenAI           | `gpt-5.6-luna`            | Low-cost summarization                                 |
| Query Expansion               | OpenAI           | `gpt-5.6-luna`            | Disabled by default; only run when router requests it  |
| Answer Generation             | OpenAI           | `gpt-5.6-luna`            | Default balanced/cost-controlled answer model          |
| Graph Entity Extraction       | OpenAI           | `gpt-5.6-luna`            | Batch-enabled; strict structured output                |
| Graph Relationship Extraction | OpenAI           | `gpt-5.6-luna`            | Batch-enabled; strict structured output                |
| Graph Community Summarization | OpenAI           | `gpt-5.6-luna`            | Cost-controlled default                                |
| GraphRAG Query Synthesis      | OpenAI           | `gpt-5.6-luna`            | Default                                                |
| Embeddings                    | OpenAI           | `qwen3-embedding:0.6b`    | Low-cost embedding default                             |
| Reranker                      | Local            | configurable BGE reranker | No API calls                                           |

Optional quality escalation:

- Allow the user to select `gpt-5.4-mini` for Answer Generation, Graph Entity Extraction, Graph Relationship Extraction, Graph Community Summarization, or difficult query synthesis.
- Do not automatically escalate to a more expensive model unless the user enables an explicit budget/quality policy.
- Default quality escalation is Off.
- `gpt-5.6-terra`, `gpt-5.6-sol`, and other high-cost models must not be default assignments.

### API cost-control rules

- Use the Batch API for non-interactive workloads where supported and operationally appropriate, especially:
  - bulk metadata extraction,
  - GraphRAG entity/relationship extraction,
  - community report generation,
  - large reindex operations.
- Interactive chat and routing use standard low-latency requests.
- Cache reusable prompt prefixes where supported.
- Store token usage and estimated cost per request, query run, workflow run, workspace, model, and layer.
- Add daily and monthly soft budget settings.
- Add warning thresholds at configurable budget percentages.
- Do not silently stop essential jobs when a soft budget is exceeded; pause cost-incurring queued work and request user action.
- Show a cost estimate before a large GraphRAG operation when enough information is available.
- Query expansion is disabled by default.
- Multi-route execution is used only when router confidence/rules require it.
- GraphRAG automatic updates are disabled by default on first installation; the user may enable threshold-based updates.
- Default GraphRAG mode after setup is manual update.
- Do not call an LLM when deterministic parsing, validation, filtering, hashing, routing rules, or retrieval logic is sufficient.

## Default operational settings

Use these initial values, all editable in Global Settings:

- maximum upload size: 100 MB
- Docling concurrency: 1
- metadata LLM concurrency: 2
- embedding concurrency: 1
- GraphRAG workspace concurrency: 1
- embedding batch size: 64
- Qdrant upsert batch size: 128
- BM25 top-k: 30
- dense top-k: 30
- fusion candidate limit: 40
- reranker input limit: 30
- final evidence top-k: 10
- GraphRAG pending-document threshold: 20
- GraphRAG automatic update: Off
- conversation direct-history window: 10 messages
- maximum retry count: 3
- successful workflow retention: 90 days
- failed/interrupted workflow retention: 180 days
- detailed workflow-event retention: 30 days
- SSE reconnect delay: 3 seconds
- health-check interval: 30 seconds
- default table page size: 50
- router multi-route mode: conservative
- automatic expensive-model escalation: Off

## First-run setup wizard

Create a setup wizard that runs when required global configuration is missing.

Steps:

1. Welcome and data-path selection
2. Service health:
   - SQLite
   - Redis
   - worker
   - Qdrant
   - optional Ollama
3. OpenAI API key configuration
4. Optional Anthropic configuration
5. Optional Ollama connection and installed-model discovery
6. Embedding model selection
7. Layer model assignment review
8. Cost-control and GraphRAG automation settings
9. Test request and final validation
10. Completion summary

Requirements:

- The wizard can be reopened from Settings.
- Ollama is optional.
- The wizard validates the OpenAI key with a minimal-cost request.
- The wizard must not expose a stored secret after saving.
- The wizard clearly shows which features remain unavailable when a provider is not configured.

## Secret storage

V1 secret policy:

- Prefer the operating-system credential store through a small secret-store abstraction.
- On Windows, support Windows Credential Manager through a maintained Python library or secure OS integration.
- Provide an environment-variable fallback for development and Docker.
- Do not store API keys as plaintext in SQLite.
- Do not return stored secrets to the frontend.
- UI displays only configured/not configured, provider, last validation time, and optional key suffix where safe.
- Logs, tracebacks, SSE events, workflow outputs, and support bundles must redact secrets.
- Document development `.env` behavior separately from production/local-user secret storage.

## Ollama management policy

V1:

- Discover and list installed models.
- Run a lightweight health/model-availability test.
- Show model size and capabilities when available.
- Show a copyable `ollama pull MODEL` command for missing optional models.
- Do not download, update, or delete Ollama models from Cortex.
- Do not use `qwen3:4b` or a smaller local model as a reliable production default.
- Optional low-resource models such as `gemma3:1b` or `qwen3:1.7b` may be shown only as experimental/offline choices with a quality warning.

## Evaluation fixture format

Create evaluation fixtures using a versioned JSONL or JSON schema containing at minimum:

- `id`
- `workspace_fixture`
- `question`
- `expected_route`
- `allowed_routes`
- `expected_document_ids`
- `expected_document_version_ids`
- `expected_facts`
- `forbidden_facts`
- `answerable`
- `expected_evidence_types`
- `notes`
- optional latency/cost budget

Create synthetic starter fixtures. Clearly document that a real 50–100 question verified set must later be created from the user's actual documents.

## Windows-specific support

The primary supported development environment is Windows 11 with Docker Desktop and WSL2.

Validate:

- host-mounted data under a configurable path such as `D:\Cortex\data`
- paths containing spaces
- Turkish characters in filenames and directories
- long-path handling
- Docker volume permissions
- line-ending consistency
- `host.docker.internal` access to Ollama
- graceful behavior when the D: drive is unavailable
- normalized internal POSIX/container paths versus Windows host paths

Never hard-code a user-specific absolute path.

## GraphRAG cost controls

Settings must include:

- automatic GraphRAG update: On/Off
- update mode: manual/threshold-based
- pending-document threshold
- maximum documents per run
- maximum estimated input tokens per run
- optional estimated-cost warning threshold
- require confirmation above a configurable estimated cost
- Batch API use for eligible GraphRAG stages
- selected model per GraphRAG stage
- cancel/pause queued GraphRAG work
- per-run token and cost report

Default:

- automatic update Off
- manual update mode
- `gpt-5.6-luna`
- confirmation required above the configured warning threshold

## Test strategy

Frontend:

- Vitest
- React Testing Library
- Playwright for end-to-end tests

Backend:

- pytest
- pytest-asyncio where needed
- integration tests against disposable Redis and Qdrant services

Contract:

- OpenAPI schema drift test
- generated TypeScript client drift test

Architecture:

- import-boundary tests
- workspace-isolation tests
- no-unfiltered-Qdrant-query tests

Performance:

- representative synthetic scale tests
- optional full 5,000-file benchmark profile

## Multilingual local embedding default

Use Ollama `qwen3-embedding:0.6b` as the generic V1 embedding default only
when it is installed. For the actual shared KnowledgeOS deployment, prefer the
installed model discovered from `/api/tags`; the current expected model is
`bge-m3:latest`.

Reasons and constraints:

- It is a dedicated embedding model, not the `qwen3:4b` chat model.
- It supports multilingual and cross-lingual retrieval.
- It is materially smaller than the larger Qwen3 embedding variants.
- It must run through Ollama's `/api/embed` endpoint.
- Cortex must test the model during setup before allowing indexing.
- If the generic model is not installed, show:
  `ollama pull qwen3-embedding:0.6b`
- Do not execute that command automatically. When the shared KnowledgeOS
  runtime already provides `bge-m3:latest`, use it rather than downloading a
  second embedding model.
- The setup wizard may offer the discovered BGE model as the active local
  embedding choice.
- OpenAI `text-embedding-3-small` remains an optional provider/model choice, not the default.

### Embedding invariants

- Store the embedding provider, model identifier, model digest/version when available, dimensions, normalization behavior, and embedding configuration hash.
- Never mix vectors generated by different embedding configurations in the same active named-vector field.
- Changing the embedding model, dimensions, prefixes, normalization, or truncation policy marks every affected workspace as outdated and requires full dense reindexing.
- Detect dimension mismatches before Qdrant upsert.
- Query and document vectors must use the same model and compatible formatting policy.
- Use cosine similarity and normalized vectors as recommended by the Ollama embedding API.
- Batch embedding requests, but dynamically reduce batch size on memory or timeout errors.
- Do not keep the embedding model permanently loaded if it causes resource pressure; make keep-alive configurable.
- Record embedding latency, throughput, failures, and effective batch size.
- Provide a setup benchmark using representative Turkish and multilingual samples.
- Block activation if the embedding health test produces invalid dimensions, NaN values, empty vectors, or inconsistent dimensions.
- Add a small retrieval-quality smoke test with Turkish exact-semantic, cross-lingual, date, name, and historical-document examples.

### Embedding text preparation

Implement a model-specific embedding adapter.

For `qwen3-embedding:0.6b`:

- Keep query and document formatting policy inside the adapter.
- Do not spread model-specific prefixes through retrieval feature code.
- Preserve Turkish characters and Unicode normalization consistently.
- Normalize line endings and control characters without rewriting source meaning.
- Use heading/title context when embedding chunks.
- Avoid embedding YAML/frontmatter noise unless selected metadata is intentionally included.
- Store the exact prepared embedding text hash for reproducibility.
- Respect the model context limit and chunk-level token budget.
