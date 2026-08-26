# Cortex Implementation Status

Codex must keep this file updated.

## Overall

- [x] Phase 1 — Repository and AI context
- [x] Phase 2 — Frontend foundation
- [x] Phase 3 — Backend foundation
- [x] Phase 4 — Database and workspace
- [x] Phase 5 — Document ingestion
- [x] Phase 6 — Retrieval and GraphRAG
- [x] Phase 7 — Jobs, workflows, and monitoring
- [x] Phase 8 — Chat and query
- [x] Phase 9 — Settings and system map
- [x] Phase 10 — Validation and hardening

## Query Architecture V2

- [x] Phase 01 — V2 architecture contract
- [x] Phase 02 — Repository boundaries and AI navigation
- [x] Phase 03 — Neo4j-backed Microsoft GraphRAG foundation
- [x] Phase 04 — Canonical knowledge model, identity, and provenance
- [x] Phase 05 — Indexing V2 / knowledge construction
- [x] Phase 06 — Conversation context and semantic query understanding
- [x] Phase 07 — Logical Query IR
- [x] Phase 08 — Execution planning
- [x] Phase 09 — Engine result and evidence layer
- [x] Phase 10 — Structured and graph query engines
- [x] Phase 11 — Reasoning, research, and composition
- [x] Phase 12 — System map V2
- [x] Phase 13 — Full reindex and sharp cutover
- [x] Phase 14 — Evaluation and acceptance
- [x] Phase 15 — Final integration audit

## Current phase

- Phase: V2 stabilization and documentation alignment
- Status: `POST /chat` is V2-only and `retrieval.grounded` is production-accepted: immutable
  generation manifests, generation-bound dense/BM25 retrieval, fusion, evidence validation,
  reconciliation, AnswerEngine ownership, and persistence are covered by the uploaded-file
  acceptance. `graphrag.grounded` is partial/readiness-dependent. `canonical.exhaustive` and
  `canonical.graph` are **not production accepted**; canonical lifecycle is incomplete.
- Next target: complete the adversarial and full-V2 acceptance suite for `canonical.exhaustive`.
  Cortex now owns Ollama 0.32.6 and the `cortex_ollama_models` volume; its persisted
  `bge-m3:latest` embedding health check succeeds at 1024 dimensions without KnowledgeOS.
  The isolated `canonical-acceptance-20260826` fixture ingestion was retried successfully.
  Candidate generation `a08ffb52-3699-4e50-8af1-2cd41e3cda0d` has ready source, BM25, dense,
  and SQLite canonical stages, but canonical SQLite status is `PARTIAL` (7 mentions, 2 safe
  properties, 2 assertions, 1 rejected assertion). It cannot be activated or used for the final
  HTTP canonical gate; no live workspace was rebuilt or cut over.
  The SQLite construction/read adapter is implemented (including `0023` surname projection and
  `0024` manifest-chunk accounting), but it is not production accepted and has not been run against
  an existing user generation.
- Started: 2026-08-21
- Last updated: 2026-08-26

## Stabilization correction

Earlier Phase 13â€“15 entries recorded implementation milestones too broadly. The acceptance suite
uses no-op canonical and GraphRAG construction stages, so it proves V2 retrieval/citation behavior,
not canonical structured population, relation/event traversal, lifecycle, or live GraphRAG
acceptance. Those capabilities must not be reported as production-ready until their own acceptance
fixtures pass.

## Completed work

- Completed V2 validation cleanup and readiness separation: retrieval activation/cutover now gates
  only immutable source, BM25, and dense/Qdrant projections. `graphrag.grounded`,
  `canonical.exhaustive`, and `canonical.graph` are independently represented as unavailable or
  ready capability families. Unavailable canonical plans return a normal V2 `ReasoningPackage` and
  AnswerEngine unsupported answer without retrieval fallback; they no longer produce a global
  request failure or block `retrieval.grounded`.

- Completed Query Architecture V2 Phase 13: a real uploaded text file now passes parsing,
  normalization, logical-document/chunk creation, immutable manifest construction, generation-owned
  BM25, generation-filtered Qdrant, readiness agreement, cutover activation, detached V2 execution,
  semantic planning, query embedding, dense+sparse RRF, EngineResult trusted-source validation,
  ReasoningPackage reconciliation, AnswerEngine citations, and normal `POST /chat` grounded and
  unsupported persistence. Production chat has no V1 branch or fallback; reachability spies prove
  zero calls to V1 ask, HybridRetrievalRuntime, and workspace-only dense search. The production
  evaluation CLI now runs this V2 uploaded-file acceptance; the old synthetic V1 benchmark is
  explicitly historical. The System Map and owning architecture/API/context documentation show
  V2-only production reality.

- Completed Query Architecture V2 Phase 14: `python -m app.evaluation` executes the isolated versioned V2 production acceptance and emits a typed `CutoverEvaluation`-compatible result. Its mandatory atomic contract is pass/fail closed (score 1.0 or 0.0) and covers upload through immutable generation artifacts, V2-only `POST /chat`, trusted citations, unsupported-answer behavior, post-activation manifest-tampering failure, generation/workspace isolation, and legacy-runtime reachability guards. The retained golden V1 runner is explicitly historical; user-supplied private verified packs may extend coverage without replacing the production contract.
- Completed GraphRAG trusted provenance bridge: V2 uses normalized generation-owned artifacts, never
  Microsoft GraphRAG CLI prose. Local, Global, and DRIFT flow through the production engine registry
  and exact-source bridge; `community_context` remains explicitly unavailable. Deterministic tests
  cover each supported mode, missing identity fields, cross-scope/unknown/tampered references,
  multi-engine reconciliation, and AnswerEngine final-prose ownership.
- Completed Query Architecture V2 Phase 15: the final production/cutover audit revalidated the
  active `POST /chat` chain, V1-fallback isolation, generation-bound reads, trusted evidence,
  final-root selection, canonical analytics, graph/event/referent execution, GraphRAG bridge,
  persistence, Git-tracked acceptance tests, current docs/System Map, and live Neo4j behavior.

- Started Query Architecture V2 Phase 13: added workspace-scoped live runtime pointers and
  immutable cutover-attempt audit records; exact-generation, fresh-corpus, schema/config/Neo4j/
  runtime, curation-preservation, and versioned evaluation gates; a deterministic Neo4j fingerprint
  over user-curated entities, aliases/tombstones, and identity operations; a read-only cutover
  status API; migration 0020; focused failure-safety, isolation, curation, API, and migration tests;
  and the corresponding System Map/architecture contracts. Rejected attempts leave the runtime
  pointer unchanged. This historical foundation preceded the completed V2-only cutover.

- Completed Query Architecture V2 Phase 12: replaced the displayed V1 intent/route-led query and
  document-flow diagrams with an exported runtime architecture manifest containing all eleven
  Query V2 and thirteen Indexing V2 subsystem groups. Each group names its real implementation
  boundary, canonical documentation, and scoped AGENTS/CLAUDE context. Execution Planning is a
  separate parent for Structured Query, Knowledge Graph, Retrieval, and GraphRAG; all engine
  outputs converge through Result & Evidence before Reasoning & Composition and Answer. Indexing
  separates canonical KG Build from the BM25, Dense/Qdrant, and GraphRAG projections and converges
  only at Generation/Readiness. The detail panel exposes boundary, guarantee, documentation, and
  AI context. V1 chat remains active; Phase 13 still owns the full rebuild and sharp cutover.
- Completed Query Architecture V2 Phase 11: added versioned durable `ResearchCheckpoint` and
  `CompositionCheckpoint` contracts backed by workspace-isolated, optimistic-revision
  `research_runs` and `composition_runs`. Research supports dependency-ordered decomposition into
  multiple Logical Query IR/physical-plan slots, reconciled evidence-package collection,
  generation isolation, cross-source grounded claims, explicit partial/unsupported state, and
  detached planner execution between short transactions. Composition supports contiguous outlines,
  independently resumable sections, paragraph/sentence provenance, collected-evidence validation,
  consistency gates, and final assembly whose sentence-evidence map must exactly match the internal
  draft. V1 chat is unchanged; Phase 12 still owns the full V2 System Map and Phase 13 owns cutover.
- Completed Query Architecture V2 Phase 05A production delivery: registered the specialized
  `knowledge_reindex` worker executor; added same-generation retry, stale-lock recovery, durable
  per-chunk extraction artifacts, strict OpenAI Structured Outputs, bounded exact-span repair and
  assertion-level rejection, conservative identity, typed canonical promotion, generation-scoped
  BM25/Qdrant/GraphRAG projections, and readiness API/UI. Live acceptance on the selected 19-chunk
  workspace activated generation `8d4665b6-7426-4abd-a95a-6df02cddc20a` only after all eleven
  checkpoints were ready (251 entities, 32 relations, 8 events, 14 temporals, 75 claims). This is
  not the Phase 13 full-corpus rebuild or Query V2 runtime cutover.

- Completed Query Architecture V2 Phase 10: added deterministic structured execution for canonical
  enumeration, filter/join/distinct/group/count and distinct count, min/max/sum/average,
  rank/top-N, sort/limit/project, temporal filter, existence, and population comparison. Added a
  concrete bounded canonical-population reader with exact candidate/confirmed counts and explicit
  unresolved/not-safely-enumerable state instead of approximate or top-k completeness. Added the
  canonical Knowledge Graph Engine for evidence-bound identity lookup, relation traversal through
  ten hops, event participation, temporal constraints, provenance traversal, and conflict
  inspection. Extended the Cortex Neo4j adapter to materialize and query workspace/generation-bound
  canonical relation, participant, and temporal links while preserving exact source lineage. Both
  engines emit Phase 09 `EngineResult`, perform no SQLite/model calls, cannot author final prose,
  and remain disconnected from V1 chat. No V2 indexing cutover, production end-to-end engine run,
  readiness UI, or corpus completeness is claimed.
- Completed Query Architecture V2 Phase 09: added versioned `EngineResult` and `ReasoningPackage`
  contracts for structured rows/entities, graph paths, aggregates, exact text evidence, GraphRAG
  findings, claims/facts, provenance, completeness, confidence, ambiguity, conflicts, failures,
  citations, and sanitized traces. Added physical-plan step/capability binding; workspace and
  generation validation; detached trusted-source exact-substring verification; fail-closed
  conflicting evidence-ID handling; compatible result/evidence deduplication; disagreement
  preservation; deterministic evidence ranking and exact citation materialization; mandatory-step,
  projection, candidate-count, and completeness validation; and explicit grounded,
  corpus-complete, partial, unsupported, and ambiguous states. Engine and reasoning schemas forbid
  final-answer fields, and reconciliation performs no external call or persistence. V1 chat and the
  current System Map remain unchanged; no V2 indexing cutover, production engine acceptance,
  readiness UI, or corpus completeness is claimed.
- Completed Query Architecture V2 Phase 08: added versioned, typed physical execution DAGs with
  explicit capability, dependency, I/O, workspace/generation/projection readiness, coverage,
  failure/fallback, and trace contracts. Added correctness-first capability selection in the fixed
  evidence/coverage/reasoning/latency/cost order; canonical structured operations; graph traversal,
  multi-hop and temporal reasoning; hybrid/semantic retrieval; GraphRAG Local/Global/DRIFT and
  community context; contradiction analysis; long-form research; ambiguity candidates; and a
  mandatory evidence reconciliation root. Exhaustive work fails closed on readiness or generation
  mismatch and cannot fall back to grounded retrieval. Planning performs no database, model, or
  engine calls. V1 chat and the current System Map remain unchanged; no V2 indexing cutover,
  production engine acceptance, readiness UI, or corpus completeness is claimed.
- Completed Query Architecture V2 Phase 07: added versioned `LogicalQueryIR` schema `1.0` with all
  nineteen required discriminated operator families, composable ambiguity candidate DAGs, explicit
  workspace scope, temporal predicates, coverage, output projection, evidence requirements, and
  governed custom capabilities. Added fail-closed schema/DAG/type/upstream-lineage/workspace/
  vocabulary/coverage/evidence validation, schema-governed dynamic relations, meaning-preserving
  safe repair, and deterministic Phase 06 semantic lowering. Exhaustive list/count/group/min/max/
  rank/top-N/population comparison cannot use discovery/top-k coverage or weak provenance. V1 chat
  and the current System Map remain unchanged pending later planning and sharp cutover phases.
- Completed Query Architecture V2 Phase 06: added durable, revisioned conversation-local context
  state isolated by workspace and conversation; bounded detached history snapshots; strict source
  message validation; a versioned semantic schema with no V2 `intent` or engine choice; configurable
  simple/standard/complex planner tiers; strict Responses JSON Schema output; bounded repair and
  state/confidence escalation; explicit ambiguity/unresolved outcomes; typed event/document/mentioned,
  range, before/after, approximate, and partial temporal semantics; and deterministic follow-up
  entity/temporal carry-over. Updated the generated settings contract and architecture/context docs.
  V1 chat remains unchanged, and neither V2 indexing cutover nor corpus completeness is claimed.
- Completed Query Architecture V2 Phase 04: added the stable upper ontology, opaque UUID canonical
  identities, original mentions, aliases, conservative evidence-based resolution, reversible
  merge/split and alias history, `user_curated > validated > extracted` precedence, exact-span
  provenance, typed relations/events/temporal expressions, evidence-gated claim/fact transitions,
  validators, and explicit retained contradictions. Extended the workspace-scoped Neo4j adapter
  with precedence-safe canonical/entity/claim persistence, evidence lineage, curation operations,
  and conflict links; added generated-contract REST endpoints and a `/knowledge` curation UI for
  merge, split, alias add/remove, evidence inspection, and history. Updated `/system-map` and the
  owning architecture/API/frontend/context documentation while keeping Phase 05 automatic
  construction explicitly inactive.
- Completed Query Architecture V2 Phase 03: pinned Neo4j Community and
  its official Python driver; added authenticated Compose/config/health integration; introduced the
  only permitted workspace-scoped Neo4j driver boundary; separated `ExtractedKnowledge` from
  `CanonicalKnowledge`; added atomic, generation-bearing GraphRAG extraction synchronization and a
  non-final typed finding envelope; versioned the durable GraphRAG workflow with `neo4j_sync`; and
  updated `/system-map`, architecture, workflow, AI context, and licensing documentation. Live
  Compose acceptance verified authenticated health, schema creation, GraphRAG persistence, and
  destructive-replacement isolation across two workspaces.
- Completed Query Architecture V2 Phase 02: added first-class `query`, `knowledge`, `engines`,
  and `reasoning` ownership packages with child boundaries, canonical scoped instructions, generated
  thin Claude adapters, project-map/index routing, and a documented no-duplication map. Existing
  `retrieval` and `graphrag` implementations remain their V2 engine boundaries, while active V1
  imports and runtime behavior remain unchanged.
- Completed Query Architecture V2 Phase 01: established the binding target architecture for
  Conversation Context, Query Understanding, Logical Query IR, Execution Planning, all four
  execution engines, the common Result & Evidence Layer, Reasoning & Composition, Answer Engine,
  canonical knowledge construction, provenance, generation readiness, and sharp-cutover policy.
  Active V1 documentation and `/system-map` remain explicitly current-state until implementation.

- Created the Git-backed Cortex monorepo skeleton and runtime-data ignore policy.
- Added canonical/scoped AI instructions, project map, adapter generator, context validation, and freshness checks.
- Added initial architecture, API, workflow, frontend, dependency, licensing, linting, and pre-commit documentation/configuration.
- Installed pinned JavaScript and Python development tooling in ignored local dependency directories.
- Started Phase 2: created the Vite/React/TypeScript shell, pinned frontend dependency graph, Tailwind and PrimeReact setup, route placeholders, UI adapters, icon registry, platform layout, appearance store, and generated-API boundary.
- Started Phase 3: added FastAPI `/api/v1` application, correlation IDs, standard error envelope, health service map, SQLite WAL/foreign-key configuration, secret-store abstraction, model defaults, and initial Docker Compose topology.
- Started Phase 4: added workspace resource/state records, WorkspaceContext, workspace CRUD/soft-delete endpoints, and the relational schema migration.
- Started Phase 5: added secure workspace uploads, document versioning and deduplication,
  Docling normalization, folder assignment, metadata provenance, chunking, and ingestion-run persistence.
- Started Phase 6: added isolated Qdrant, hybrid-retrieval, embedding, and GraphRAG adapter
  boundaries; deterministic vector IDs; common evidence/answer-state models; GraphRAG artifact
  and rebuildable NetworkX support; retrieval migration and focused adapter tests.
- Completed Phase 6's persistent per-workspace bm25s boundary, configurable hybrid-retrieval
  limits, and local-only BGE reranker adapter. Hybrid Search now remains available while a
  workspace graph is absent or stale.
- Added the worker-owned Microsoft GraphRAG CLI adapter for workspace-isolated index execution
  and distinct Local, Global, and DRIFT queries. The native GraphRAG workspace output remains
  canonical; Qdrant and NetworkX continue as separately rebuildable projections.
- Wrapped each GraphRAG route as a separate LlamaIndex `CustomQueryEngine`, preserving normalized
  evidence as workspace-scoped source nodes for the future router.
- Added explicit stale-graph signaling when an upstream query fails, allowing a future router to
  fall back safely to Hybrid Search without representing stale output as grounded evidence.
- Added embedding-configuration fingerprints that include model, digest, dimensions,
  normalization, and text-template version. Dense Qdrant reads/writes are configuration-filtered;
  a changed configuration records a full-reindex requirement and blocks incompatible dense search.
- Added a testable Ollama `/api/embed` health check and a dedicated Qwen3 query/document
  preparation adapter that preserves Turkish Unicode and normalizes line endings.
- Added a workspace-isolated GraphRAG input materializer for active normalized document versions;
  the future deferred-update worker can use its manifest without mixing workspace inputs.
- Added GraphRAG workspace initialization through the supported CLI, producing the workspace's
  own `settings.yaml` before worker-owned input materialization and index execution.
- Completed the deferred GraphRAG update stages, including transaction-safe input snapshotting,
  opt-in eligible Batch API stage planning, NetworkX rebuilding, and canonical-output mirroring
  into workspace-isolated Qdrant collections. Added durable, idempotent dense-reindex requests
  plus Turkish/cross-lingual and BGE-M3 adapter smoke coverage.
- Started Phase 7: added versioned durable workflow definitions, SQLite run/step/event state,
  workspace locks, Dramatiq execution/restart recovery, REST commands, an SSE event stream,
  a React Flow-backed process view, EventSource reconnect/state restoration, stage concurrency
  caps, retention cleanup, idempotent relational deletion checkpoints, and secret redaction in
  persisted workflow errors. Added tested LlamaIndex ingestion and reindex workflow definitions
  that isolate the normalized-document and workspace-scoped reindex handoffs, plus separate
  durable query-run and query-step records for the chat phase. The process UI now supports
  selecting runs, grouped step details, recovery actions, and a sanitized technical-error dialog
  backed by event history. Global shell progress is restored independently of the processes page.

- Completed Phase 8: added an actual LlamaIndex RouterQueryEngine builder with a constrained
  selector, worker-owned OpenAI Responses synthesis and conversation summary calls, inference
  labels, memory-window summaries, source-details dialog, message pagination, soft-budget
  pausing, token/cost recording, query-latency capture, and generated OpenAPI Chat types.
- Added entity-document lookup planning and synthesis: Turkish/English document-list questions
  now set `entity_document_lookup` and `needs_list`, exact entity matches are prioritized, chunks
  are grouped into unique document results with identity metadata, and answers emit one concise
  row and citation per document.
- Updated the System Map query flow with the document-list intent decision and unique-document
  grouping branch. The Processes page remains unchanged because the feature uses the existing
  persisted `route`, `retrieve`, and `synthesize` query steps.
- Completed the multi-document DOCX ingestion audit and correction. DOCX Word Heading 2 styles
  are normalized to Markdown `##`, and the splitter uses only those headings—never archive-code
  prefixes—to create first-class logical documents with code/title/type/source/page metadata;
  chunks cannot cross logical boundaries; GraphRAG materializes one input per logical document
  and resolves entity
  provenance through text units; retrieval returns logical codes; and a workspace-scoped
  ingestion diagnostics endpoint exposes the source-to-retrieval trace. Ingestion workflow v3
  and the System Map/Processes flows include the logical-document checkpoint.
- Completed the worker-owned GraphRAG query protocol. The API persists and submits a durable
  QueryRun through Redis/Dramatiq, while the GraphRAG-capable worker resolves persisted selected
  settings, executes Local/Global/DRIFT outside a SQLite write transaction, and records the final
  native answer, evidence, trace, and stage usage. Bounded API waits fail safely without allowing
  a late worker result to overwrite a terminal timeout; GraphRAG final answers bypass synthesis.
- Updated the System Map with the durable GraphRAG query boundary, explicit-fallback path,
  optional default-off claims, algorithmic community detection, and user-selected community report
  generation.
- Wired ordinary `hybrid` chat routes and the opt-in GraphRAG fallback to the real
  workspace-scoped `HybridRetriever` runtime (configured embeddings, Qdrant, persisted BM25,
  RRF, optional local reranker, evidence limits, citations, and sanitized retrieval trace data).
- Completed Phase 3.2 answer-stage evidence selection: HybridRetriever remains broad, while a
  deterministic operation-aware selector promotes resolved full-name descriptive evidence,
  penalizes numeric/OCR shorthand and stubs, filters unrelated identity evidence, applies
  document diversity, and emits a short inspectable selection trace. Identity, description, and
  timeline answers have independent final-evidence limits; citations now derive only from that
  selected ordering. Normal hybrid fallbacks and synchronous OpenAI synthesis persist explicit
  eligibility, attempt, success, provider/model, fallback, and safe-error metadata.
- Completed Phase 3.3 concise answer rendering: normal structured QA now returns a small
  operation-aware local fallback instead of raw chunk excerpts. Synchronous synthesis reads cited
  chunks only as internal context, receives a strict paraphrase-and-inline-citation contract, and
  applies a deterministic copied-span guard with one regeneration attempt. Metadata records the
  guard and regeneration outcomes.

## Prior milestones and ongoing backlog
- Completed the Phase 13 immutable generation source-manifest prerequisite: candidate snapshots now write deterministic generation-owned JSONL source manifests, persist their URI/SHA-256/count, and prove BM25/Qdrant membership and content identity against that manifest before readiness. Trusted-source loading fails closed on missing, tampered, malformed, foreign, duplicate, or content-inconsistent manifests. This was the prerequisite checkpoint; no pointer changed at that time.

- Phase 13 full rebuild delivery completed for both active local workspaces: each candidate has one
  active exact-generation checkpoint set after real BM25, Qdrant, and GraphRAG execution. The V2
  Answer Engine rendering boundary now accepts only reconciled ReasoningPackage input; the live
  orchestration/evaluation gate and sharp runtime activation remain incomplete.
- Phase 13 now has a reusable production composition root. Persisted workspace/conversation state
  is detached by `V2RuntimeContextLoader`; one fixed generation then feeds the configured semantic
  planner/query embedder, generation-filtered Qdrant, candidate-owned BM25, `V2PlanExecutor`, RRF
  bridge, trusted manifest, reconciliation, `ReasoningPackage`, and `AnswerEngine`. Internal
  grounded, lexical, semantic, dense+sparse fusion, no-evidence, workspace/generation isolation,
  and pointer-snapshot acceptance passes with deterministic external-provider adapters. V1 remains
  live; uploaded-file production acceptance, API cutover, evaluation, and activation are pending.
- Added a deterministic golden-question evaluation subsystem with versioned synthetic suites,
  production chat orchestration, layer-specific diagnostics, retrieval metrics, and CLI output.
- Completed structured query planning, workspace-evidence entity resolution, bounded resolved-name
  retrieval expansion, operation-aware evidence selection, synchronous OpenAI hybrid synthesis,
  and query-plan debug output. COUNT/LIST answers explicitly retain aggregation/completeness
  uncertainty until their deferred execution layers exist.
- Deferred by user decision: production OpenAI/Anthropic request adapters and automatic provider-reported token counting. See `docs/FUTURE_BACKLOG.md`.

## Blocking issues

- None for Phase 15.

## Validation history

| 2026-08-25 | V2 validation cleanup and canonical readiness separation | 44 focused runtime-input/planning/AnswerEngine/cutover/construction/GraphRAG tests; touched-file Ruff; focused System Map tests; alternate-output Vite build; context validation; `git diff --check` | Passed. Standard frontend build output remains externally locked at `frontend/dist/logo.png`; the same build succeeded to a temporary alternate output directory, which was removed. |
| 2026-08-23 | Query V2 final production/cutover audit | 133 focused Query V2 tests; 12 live Neo4j tests with zero skips; 25 focused GraphRAG tests; 3 uploaded-file/production-evaluation tests; full 9-test frontend/System Map suite; Query V2 Ruff; frontend lint/build; context validation; staged and unstaged `git diff --check` | Passed (known local-Qdrant payload-index, Pydantic field-attribute, and Vite bundle-size warnings only) |
| 2026-08-23 | GraphRAG trusted provenance bridge | 31 focused GraphRAG adapter/V2 bridge/plan-executor tests; touched-file Ruff; 9 frontend tests including System Map; context validation; staged and unstaged `git diff --check` | Passed (one existing Pydantic field-attribute warning) |
| 2026-08-22 | Query Architecture V2 Phase 15 final integration audit | 57 focused V2 runtime/planning/bridge/reconciliation/answer/cutover/acceptance tests; full backend pytest (341 passed, 2 skipped); complete backend Ruff; 9 frontend tests; frontend lint/build; generated 26 AI-context adapters; context validation; `git diff --check` | Passed (local-Qdrant payload-index, Pydantic, LlamaIndex deprecation, and Vite bundle-size warnings only) |
| 2026-08-22 | Query Architecture V2 Phase 14 evaluation and acceptance | `python -m app.evaluation`; full backend pytest with deterministic keyring/Ollama environment (340 passed, 2 skipped); complete backend Ruff; fresh in-memory SQLite Alembic upgrade; context validation; `git diff --check` | Passed (local-Qdrant payload-index, Pydantic, and LlamaIndex deprecation warnings only; one mandatory versioned production contract) |
| 2026-08-22 | Query Architecture V2 Phase 13 final V2-only cutover | Real uploaded-file production evaluation; 144 focused Phase 13/ingestion/chat/migration tests; 337 broader backend tests with 2 skips and the isolated historical V1 orchestration case deselected; Ruff app/touched tests; compileall; 9 frontend tests; System Map test; frontend lint/build; generated 26 AI-context adapters; context validation; git diff --check | Passed (local Qdrant payload-index, Pydantic, LlamaIndex deprecation, and Vite bundle-size warnings only) |
| 2026-08-22 | Query Architecture V2 Phase 13 production composition | 105 focused factory/runtime/retrieval/manifest/reconciliation/AnswerEngine/planner/IR/generation tests; deterministic persisted-state acceptance; Black; Ruff; py_compile; V1 reachability audit; generated 26 AI-context adapters; context validation/freshness; git diff --check | Passed (local in-memory Qdrant payload-index warning only; V1 routing and production pointers unchanged) |
| 2026-08-21 | Query Architecture V2 Phase 13 cutover foundation | Ruff; 21 focused cutover/API/Neo4j/generation tests; 2 fresh/upgrade migration tests; local schema revision 0020; live Neo4j curation-fingerprint smoke; 9 frontend/System Map tests; generated OpenAPI types; frontend production build/lint; generated 26 AI-context adapters; context validation/freshness; git diff --check | Passed (existing Vite bundle-size advisory; full rebuild/runtime activation still open) |
| 2026-08-21 | Query Architecture V2 Phase 13 planner live smoke | One selected-model, detached semantic-planner request against a rebuilt workspace | Valid strict-schema output, but unresolved; blocked because no workspace corpus/schema awareness or retrieval execution bridge |
| 2026-08-21 | Query Architecture V2 Phase 13 generation-bound dense skeleton | Immutable GenerationScope; dormant physical-plan executor; generation-bound Qdrant read and adversarial execution isolation tests | Passed (internal only; V1 live; BM25/reconciliation/activation pending) |
| 2026-08-21 | Query Architecture V2 Phase 13 generation-bound BM25 read | Candidate-owned BM25 loader/identity validation; dormant sparse adapter; sparse isolation, no-fallback, mismatch, and pointer-snapshot tests; dense executor and retrieval regression | Passed (internal only; V1 live; fusion/reconciliation/activation pending) |
| 2026-08-21 | Query Architecture V2 Phase 12 | Exported 24-group runtime manifest acceptance; 2 focused System Map tests; 9 complete frontend tests; production TypeScript/Vite build; ESLint; generated 26 AI-context adapters; context validation/freshness; `git diff --check` | Passed (existing Vite bundle-size advisory only) |
| 2026-08-18 | Query Architecture V2 Phase 11 | Ruff; 97 focused backend regression tests across Phases 05A and 06-11, including four durable research/composition tests and migration acceptance; final 18-test Phase 05A/11 gate; 8 frontend tests; frontend production build/lint; generated context adapters; context validation/freshness; `git diff --check` | Passed (existing Vite bundle-size warning only) |
| 2026-08-18 | Query Architecture V2 Phase 05A production delivery | Selected-model live 19-chunk candidate completed all eleven readiness stages and activated generation `8d4665b6-7426-4abd-a95a-6df02cddc20a`; 392 evidence spans, 251 mentions/canonical entities, 32 relations, 8 events, 14 temporals, 75 claims, 19 BM25 chunks, 19 Qdrant chunks, and GraphRAG ready; 2 opt-in live Neo4j tests; focused backend/API and frontend readiness tests | Passed (temporary HTTP smoke check was not run; no V2 cutover or corpus-completeness claim) |
| 2026-08-18 | Query Architecture V2 Phase 10 | Ruff; 83 focused backend tests covering detached canonical populations, surname filtering, exact list/count/distinct/group/min/max/rank/top-N/projection/population comparison, bounded uncertainty, population adapter scope, EngineResult evidence, canonical identity resolution, multi-hop/event/temporal/provenance/conflict graph execution, Neo4j canonical edge materialization and workspace/generation/hop bounds, Phase 06–09 and V1 query regression; 8 frontend/System Map tests; context validation/freshness; `git diff --check` | Passed |
| 2026-08-18 | Query Architecture V2 Phase 09 | Ruff; 55 focused backend tests covering EngineResult/ReasoningPackage answer ownership, planned-step binding, workspace/generation isolation, exact-span traceability, trusted-source validation, compatible deduplication, disagreement preservation, GraphRAG finding grounding, evidence ranking, completeness/projection gates, ambiguity and partial-failure visibility, Phase 06–08 and V1 query regression; 8 frontend/System Map tests; context validation/freshness; `git diff --check` | Passed |
| 2026-08-18 | Query Architecture V2 Phase 08 | Ruff; 41 focused backend tests covering typed physical DAGs, exhaustive generation/projection readiness, workspace isolation, dependent and parallel multi-engine composition, GraphRAG modes, temporal/contradiction/research capabilities, ambiguity, fallback quality ordering, Phase 06/07 and V1 query regression; 8 frontend/System Map tests; context validation/freshness; `git diff --check` | Passed |
| 2026-08-18 | Query Architecture V2 Phase 07 | Ruff; 41 focused backend tests covering every operator family, schema/DAG/type/workspace/vocabulary/coverage/evidence rejection, ambiguity, temporal lowering, safe repair, Phase 06 and V1 query regression; System Map test; context validation/freshness; `git diff --check` | Passed (existing Pydantic warning only) |
| 2026-08-18 | Query Architecture V2 Phase 06 | Ruff; 36 focused backend tests including migration, workspace/conversation isolation, strict semantic schema, repair/escalation, temporal/carry-over and V1 chat regression; generated OpenAPI client; System Map test; frontend build/lint; context validation/freshness; `git diff --check` | Passed (existing Pydantic and bundle-size warnings only) |
| 2026-08-18 | Query Architecture V2 Phase 05 foundation | Ruff; 31 focused backend tests including empty migration, generation mismatch/failure/workspace isolation and exact-span extraction; 8 frontend tests; context validation; `git diff --check` | Passed |
| 2026-08-18 | Query Architecture V2 Phase 04 | Ruff; 65 focused backend tests; live Neo4j precedence/curation/exact-provenance/conflict acceptance; regenerated OpenAPI client; 8 frontend tests; frontend build/lint; context validation/freshness; `git diff --check` | Passed (existing Pydantic and bundle-size warnings only) |
| 2026-08-18 | Query Architecture V2 Phase 03 | `neo4j:2026.07.1` Compose health; authenticated live GraphRAG sync/schema/two-workspace isolation; Ruff; 49 focused tests plus opt-in live acceptance; System Map test; frontend build/lint; `uv lock --check`; quiet Compose config; context validation/freshness; `git diff --check` | Passed (existing Pydantic and bundle-size warnings only) |
| 2026-08-18 | Query Architecture V2 Phase 02 | scoped package import smoke; 33 focused query/retrieval/GraphRAG tests; context validation/freshness; `git diff --check` | Passed (2 existing warnings) |
| 2026-08-17 | Query Architecture V2 Phase 01 | `python scripts/ai-context/validate-context.py` and `git diff --check` | Passed |

| 2026-08-15 | Phase 4.4 entity-bound facts | focused ruff/pytest, context validation, and `git diff --check` | Passed (31 focused tests; existing upstream Pydantic warning) |

| 2026-08-15 | Phase 4.3 share/entity binding | `uv run black`, focused ruff/pytest, context validation, and `git diff --check` | Passed (28 focused tests; existing upstream Pydantic warning) |

| 2026-08-15 | Phase 4.2 describe/citations | `uv run black`, focused ruff/pytest, context validation, and `git diff --check` | Passed (22 focused tests; existing upstream Pydantic warning) |

| 2026-08-15 | Phase 4.1 cadastral accuracy | `uv run black`, focused ruff/pytest, context validation, and `git diff --check` | Passed (19 focused tests; existing upstream Pydantic warning) |

| 2026-08-15 | Phase 4 aggregation | `uv run black`, focused ruff/pytest, context validation, and `git diff --check` | Passed (16 focused tests; existing upstream Pydantic warning) |

| Date | Phase | Command | Result |
| 2026-08-14 | Structured query understanding | `ruff check --no-cache app/chat app/api/chat.py tests/test_chat.py tests/test_query_plan.py`, focused pytest, context validation, and `git diff --check` | Passed (11 focused tests; existing upstream Pydantic warning) |
| 2026-08-15 | Phase 3.2 | `uv run ruff check app/chat app/core/config.py tests/test_chat.py tests/test_evidence_selection.py`; `uv run pytest -q tests/test_chat.py tests/test_query_plan.py tests/test_evidence_selection.py -p no:cacheprovider`; context validation; `git diff --check` | Passed (16 focused tests; one existing upstream Pydantic warning) |
| 2026-08-15 | Phase 3.3 | `uv run ruff check app/chat app/core/config.py tests/test_chat.py tests/test_evidence_selection.py`; `uv run pytest -q tests/test_chat.py tests/test_query_plan.py tests/test_evidence_selection.py -p no:cacheprovider`; context validation; `git diff --check` | Passed (18 focused tests; one existing upstream Pydantic warning) |
| ---- | ----- | ------- | ------ |
| 2026-08-10 | Retrieval wiring | `uv run ruff check ...`, `uv run pytest -q tests/test_chat.py tests/test_retrieval.py -p no:cacheprovider`, and Alembic upgrade (from `backend`) | Passed (25 focused tests; warnings only) |
| 2026-08-08 | 8 | `uv run ruff check app tests alembic` and `uv run pytest -q -p no:cacheprovider` (from `backend`) | Passed (106 tests; upstream/local-adapter warnings only) |
| 2026-08-08 | 8 | `python scripts/ai-context/validate-context.py` and `git diff --check` | Passed |
| 2026-08-08 | 8 | `corepack pnpm test -- ASystemMap.test.tsx`, `corepack pnpm build`, and `corepack pnpm lint` (from `frontend`) | Passed (6 tests; bundle-size advisory only) |
| 2026-08-08 | 5-8 | `uv run ruff check app tests alembic`, `uv run pytest -q -p no:cacheprovider`, in-memory Alembic upgrade, and `uv lock --check --offline` (from `backend`) | Passed (112 tests; upstream/local-adapter warnings only) |
| 2026-08-08 | 2 | `corepack pnpm test`, `corepack pnpm build`, and `corepack pnpm lint` (from `frontend`) | Passed (6 tests; bundle-size advisory only) |
| 2026-08-02 | 1 | `python scripts/ai-context/generate-adapters.py` | Passed |
| 2026-08-02 | 1 | `python scripts/ai-context/validate-context.py` | Passed |
| 2026-08-02 | 1 | `python scripts/ai-context/check-context-freshness.py` | Passed |
| 2026-08-02 | 1 | `pre-commit run --all-files` | Passed |
| 2026-08-02 | 1 | `python scripts/license-report.py` | Passed; generated declared-dependency inventory |
| 2026-08-02 | 2 | `corepack pnpm --dir frontend build` | Passed |
| 2026-08-02 | 2 | `corepack pnpm --dir frontend test` | Passed (1 test) |
| 2026-08-02 | 2 | `corepack pnpm --dir frontend lint` | Passed |
| 2026-08-02 | 2 | adapter-boundary search | Passed; no feature-level PrimeReact, lucide-react, or React Flow imports |
| 2026-08-02 | 3 | `python -m pytest tests -q` (from `backend`) | Passed (1 test) |
| 2026-08-02 | 3 | `alembic -c alembic.ini upgrade head` (from `backend`) | Passed |
| 2026-08-02 | 3 | `ruff check app tests alembic` (from `backend`) | Passed |
| 2026-08-02 | 3 | `python -m pytest tests -q` (from `backend`) | Passed (3 tests) |
| 2026-08-02 | 3 | `docker compose -f infrastructure/docker-compose.yml config` | Passed |
| 2026-08-02 | 3 | `GET /api/v1/health` via Docker Compose | Passed; backend, SQLite, Redis, Qdrant, Ollama, and worker healthy |
| 2026-08-02 | 3 | `corepack pnpm api:generate` | Passed; generated OpenAPI TypeScript schema |
| 2026-08-02 | 4 | `python -m pytest tests -q -p no:cacheprovider` (from `backend`) | Passed (9 tests) |
| 2026-08-02 | 4 | Alembic upgrade from empty SQLite and from revision `0002_usage_records` | Passed; prior data preserved |
| 2026-08-02 | 6 | `python -m pytest tests -q -p no:cacheprovider` (from `backend`) | Passed (38 tests) |
| 2026-08-02 | 6 | `CORTEX_DATABASE_URL=sqlite:///:memory: alembic -c alembic.ini upgrade head` | Passed; revision `0007_graphrag_stage_reports` applies |
| 2026-08-02 | 6 | `CORTEX_DATABASE_URL=sqlite:///:memory: alembic -c alembic.ini upgrade head` | Passed; revision `0006_retrieval_embedding_state` applies |
| 2026-08-02 | 6 | `python scripts/ai-context/validate-context.py` | Passed |
| 2026-08-03 | 6 | `uv run ruff check app/retrieval app/core/config.py tests/test_retrieval.py` (from `backend`) | Passed |
| 2026-08-03 | 6 | `uv run pytest -q tests/test_retrieval.py` (from `backend`) | Passed (9 tests) |
| 2026-08-03 | 6 | `uv run ruff check app/graphrag tests/test_graphrag_adapter.py` (from `backend`) | Passed |
| 2026-08-03 | 6 | `uv run pytest -q tests/test_graphrag_adapter.py tests/test_graphrag_qdrant.py tests/test_graphrag_updates.py` (from `backend`) | Passed (6 tests) |
| 2026-08-03 | 6 | `uv run pytest -q -p no:cacheprovider` (from `backend`) | Passed (44 tests; local Qdrant payload-index warning only) |
| 2026-08-03 | 6 | `CORTEX_DATABASE_URL=sqlite:///:memory: uv run alembic -c alembic.ini upgrade head` (from `backend`) | Passed |
| 2026-08-03 | 6 | `uv run pytest -q tests/test_graphrag_adapter.py` (from `backend`) | Passed (5 tests; upstream Pydantic warning only) |
| 2026-08-03 | 6 | `uv run pytest -q tests/test_graphrag_adapter.py` (from `backend`) | Passed (6 tests; upstream Pydantic warning only) |
| 2026-08-03 | 6 | `uv run pytest -q tests/test_retrieval.py` (from `backend`) | Passed (12 tests; local Qdrant payload-index warning only) |
| 2026-08-03 | 6 | `uv run pytest -q tests/test_embeddings.py` (from `backend`) | Passed (4 tests) |
| 2026-08-03 | 6 | `uv run pytest -q -p no:cacheprovider` (from `backend`) | Passed (51 tests; upstream Pydantic and local-Qdrant warnings only) |
| 2026-08-03 | 6 | `uv run pytest -q tests/test_graphrag_adapter.py` (from `backend`) | Passed (7 tests; upstream Pydantic warning only) |
| 2026-08-03 | 6 | `uv lock --check --no-cache; uv run pytest -q -p no:cacheprovider; CORTEX_DATABASE_URL=sqlite:///:memory: uv run alembic -c alembic.ini upgrade head` (from `backend`) | Passed (56 tests; warnings only) |
| 2026-08-03 | 6 | `uv run python scripts/ai-context/validate-context.py; uv run python scripts/ai-context/check-context-freshness.py` | Passed |
| 2026-08-03 | 7 | focused workflow lint/tests and in-memory Alembic upgrade | Passed (4 tests) |
| 2026-08-03 | 7 | `corepack pnpm build && corepack pnpm lint` (from `frontend`) | Passed (bundle-size advisory only) |
| 2026-08-04 | 10 | `uv run ruff check app tests alembic` and `uv run pytest -q -p no:cacheprovider` (from `backend`) | Passed (93 tests; upstream/local-adapter warnings only) |
| 2026-08-04 | 10 | Fresh in-memory SQLite Alembic migration | Passed |
| 2026-08-04 | 10 | Frontend unit/build/lint/Playwright suite | Passed (6 unit tests, 2 E2E tests; bundle-size advisory only) |
| 2026-08-04 | 10 | Live Compose health, GraphRAG image-boundary, OpenAPI client, context, and license checks | Passed; backend/SQLite/Redis/Qdrant/worker healthy; GraphRAG worker-only |
| 2026-08-03 | 10 | `uv run ruff check app tests alembic && uv run pytest -q -p no:cacheprovider` (from `backend`) | Passed (77 tests; upstream/local-adapter warnings only) |
| 2026-08-03 | 10 | `CORTEX_DATABASE_URL=sqlite:///:memory: uv run alembic -c alembic.ini upgrade head` (from `backend`) | Passed |
| 2026-08-03 | 10 | `corepack pnpm test && corepack pnpm build && corepack pnpm lint` (from `frontend`) | Passed (5 tests; bundle-size advisory only) |
| 2026-08-03 | 10 | `docker compose -f infrastructure/docker-compose.yml up -d --no-build` and live health checks | Passed; frontend HTTP 200 and backend/SQLite/Redis/Qdrant/worker healthy |
| 2026-08-03 | 10 | `docker compose -f infrastructure/docker-compose.yml restart worker` | Passed; worker restarted and backend remained healthy |
| 2026-08-03 | 9 | `uv run pytest -q tests/test_settings.py tests/test_uploads.py tests/test_metadata.py tests/test_health.py tests/test_migrations.py` (from `backend`) | Passed (13 tests) |
| 2026-08-03 | 9 | `uv run ruff check app/core/config.py app/core/settings_service.py app/api/settings.py app/api/health.py app/chat/execution.py tests/test_settings.py` (from `backend`) | Passed |
| 2026-08-03 | 9 | `corepack pnpm build && corepack pnpm lint` (from `frontend`) | Passed (bundle-size advisory only) |
| 2026-08-03 | 7 | context validation and freshness checks | Passed |
| 2026-08-03 | 7 | focused workflow, LlamaIndex, API, and migration validation | Passed (9 tests; upstream Pydantic warnings only) |
| 2026-08-03 | 7 | `corepack pnpm build && corepack pnpm lint` (from `frontend`) | Passed (bundle-size advisory only) |

## High-risk boundary status

- [x] GraphRAG–Qdrant adapter validated
- [x] SQLite concurrency validated
- [x] OpenAPI client generation validated
- [x] Crash recovery validated
- [x] Upload security validated
- [x] Orphan reconciliation validated
- [x] 5,000-file performance baseline documented
- [x] Third-party license notices complete

## Setup, model, and cost-control status

- [x] First-run setup wizard complete
- [x] Secure secret storage complete
- [x] Default model profile seeded
- [x] OpenAI cost accounting complete
- [x] Budget controls complete
- [x] GraphRAG cost controls complete
- [x] Windows compatibility validated
- [x] Evaluation fixture schema validated

## Multilingual embedding status

- [x] qwen3-embedding:0.6b default configured
- [x] Ollama embedding health check complete
- [x] Turkish retrieval smoke tests complete
- [x] Cross-lingual retrieval smoke tests complete
- [x] Embedding configuration migration/reindex validated
- [x] Qdrant dimension safeguards validated
