# GraphRAG Boundary

## Query V2 ownership

`app/graphrag/` remains the Microsoft GraphRAG implementation and adapter boundary during V2. It is
not copied under `app/engines/`; future typed composition belongs to `app/engines/hybrid/`, while
the Neo4j-backed adapter work remains owned here. The Phase 02 scaffold changes navigation only.

Microsoft GraphRAG is an extracted-knowledge producer exposed through a dedicated adapter with
explicit schemas and integration tests; it is not canonical truth in V2. Each workspace owns an
isolated GraphRAG root, while Qdrant resource types remain separate and every operation uses the
workspace filter. Neo4j is the persistent/queryable canonical graph store; NetworkX remains a
secondary visualization projection.

## Neo4j-backed extraction path

GraphRAG reindex workflow v2 adds a durable `neo4j_sync` checkpoint after native indexing and
before Qdrant mirroring. `Neo4jBackedGraphRAGAdapter` converts entities, reports, text units,
documents, and resolvable relations into provenance-bearing nodes/edges. Query V2 reads only the
fixed `knowledge-candidates/<generation>/graphrag` artifact root. Its
`GraphRAGProductionEngine` invokes `GraphRAGAdapter.query_findings`, then the fail-closed
`bridge_graphrag` validates workspace, generation, document, version, logical document, chunk,
and content hash against `TrustedSource` before emitting an `EngineResult`. Native artifacts carry no
Cortex identity, so `query_findings` traces them through GraphRAG's own outputs: the production
stage writes one `<chunk_id>.md` input per Cortex chunk, so an entity's `text_unit_ids` (Local) or
a report's community `text_unit_ids` (Global/DRIFT) lead to `documents.parquet` titles and thus to
manifest chunks. The content hash is computed from the text GraphRAG indexed, so a stale or altered
input fails the bridge.

Smart selection (`app/graphrag/smart_search.py`, opt-in via `graphrag_smart_search_enabled`) runs
only GraphRAG's context-selection step in-process, in a private event loop, and returns entity or
report IDs; provenance and validation are unchanged. Cost controls: the answer-writing step is
skipped, Global rates short community summaries (`dynamic_search_use_summary`, one repeat),
selections are cached per generation, route, normalized question, and model, and estimated token
usage is recorded as `graphrag_search`. Local/Global/DRIFT model assignments and DRIFT limits are
query-time settings and no longer mark the graph for reindexing. GPT-5 family OpenAI models are
routed through GraphRAG's LiteLLM `chat` provider, because the `openai_chat` provider sends
`max_tokens`, which those models reject. When the `graphrag` package is not installed (for example
the API container image), selection stays lexical. The Microsoft CLI
native answer has no such exact source identity and is never admitted to Query V2. The Cortex-owned
`Neo4jGraphAdapter` atomically replaces only the current workspace's `ExtractedKnowledge` layer and
never deletes `CanonicalKnowledge`. Every node and relation carries workspace, layer, generation,
external ID, original GraphRAG attributes, and available logical-document provenance.

Upstream Microsoft GraphRAG 2.6 has no native Neo4j storage provider. Cortex therefore preserves
native Parquet/JSON as the Local/Global/DRIFT runtime source while synchronizing the extracted view
to Neo4j through its adapter. `GraphRAGEngineOutput` is the non-final typed finding contract for the
later Result & Evidence cutover. Production V2 GraphRAG now uses the trusted bridge, but remains
partial/readiness-dependent rather than production-accepted end to end.

## Upstream compatibility and limitations

`app/graphrag/adapter.py` is a version-tolerant adapter over canonical GraphRAG output
artifacts. It does not rewrite GraphRAG's native outputs: it reads normalized `entities`,
`relationships`, `reports`, and `text_units` artifacts from the workspace root and mirrors
the resource types independently through `app/graphrag/qdrant.py`. The mirror accepts only
`entities`, `reports`, and `text_units`, each in its own shared collection and always through
the workspace-safe Qdrant adapter. Local, Global, and DRIFT are separate routes at this boundary.

Microsoft GraphRAG 2.6's supported CLI is invoked through `MicrosoftGraphRAGRunner` with a
workspace root, explicit configuration path, and one of the `standard`, `fast`,
`standard-update`, or `fast-update` methods. Its `local`, `global`, and `drift` query methods
remain separate adapter calls. The runner is worker-owned: it must never execute inside an API
request or a database transaction.

`GraphRAGInputMaterializer` writes one input Markdown file per active logical document, not one
per uploaded source container. Each input carries logical ID, document code, title, type, source
filename, page range, and its normalized segment, so GraphRAG text units and extracted entities
retain the `B-2/i -> MERTER B.docx` provenance chain. Legacy versions without logical rows retain
the safe one-input-per-version fallback. The materializer remains workspace-isolated and worker
code can write its collected snapshot without holding a database transaction open. Each write
replaces prior generated Markdown inputs, preventing an old source-level file from being indexed
alongside its logical-document replacements.

`GraphRAGAdapter.initialize()` invokes the supported GraphRAG `init` command only for that
workspace root and records the resulting `settings.yaml` for the later worker-owned index call.
It configures GraphRAG's text loader with an explicit Markdown (`*.md`) pattern, matching the
normalized Markdown files materialized by Cortex; the pattern uses `\Z` rather than `$` because
GraphRAG expands settings through Python templates. It sets the GraphRAG tokenizer field to the
stable `cl100k_base` encoding independently of the selected chat or embedding provider, so local
model identifiers are never passed to tiktoken. It never writes provider secrets: the worker
passes the configured OpenAI credential to the GraphRAG CLI only through `GRAPHRAG_API_KEY` in the
subprocess environment.

GraphRAG 2.6's `create_final_text_units` workflow can leave Arrow arrays inside object-valued
`entity_ids` cells, which upstream Pandas cannot serialize to Parquet. The worker invokes GraphRAG
through `app.graphrag.cli`, a narrow compatibility entry point that converts only nested Arrow
arrays to equivalent Python lists immediately before the upstream artifact writer runs. The worker
pins `pandas==2.2.3` and `pyarrow==17.0.0`; canonical GraphRAG artifacts, workflow order, and
schemas remain upstream-owned.

On Windows host development, the CLI preloads CPU PyTorch before importing GraphRAG's scientific
stack. This avoids the intermittent `c10.dll` initialization failure that can occur when PyArrow
loads first. The adapter also decodes upstream diagnostics with replacement characters so a
Windows console-encoding mismatch cannot hide the actionable GraphRAG error.

Qdrant artifact mirroring has no client-side HTTP deadline. Creating a collection or persisting
a large GraphRAG batch may exceed ordinary request timeouts; the worker waits for Qdrant's result
and records an actual storage failure rather than failing the index solely because the response is
slow.

The selected local Ollama embedding provider also has no HTTP deadline during durable indexing.
This permits cold model loading and large artifact batches to complete; cancellation remains a
workflow-level concern rather than a client-side read timeout.

The API reads the same canonical Parquet artifacts for the bounded Graph explorer projection, so
`pyarrow==17.0.0` is an API dependency as well as a worker runtime dependency. This prevents the
read-only graph endpoint from returning an internal error when GraphRAG artifacts are present.

Deferred updates have three explicit stages: prepare the workspace snapshot and mark the graph
indexing in SQLite; run input materialization, GraphRAG index, and NetworkX rebuild with no
database session open; then record ready or stale state. Successful canonical outputs are mirrored
by `mirror_graph_outputs` into the separately filtered entity, report, and text-unit Qdrant
collections. Batch mode is opt-in and applies only to the non-interactive entity-extraction and
community-summarization stages. GraphRAG 2.6 itself exposes embedding batches but no upstream
OpenAI Batch API executor, so provider-specific Batch submission stays behind this plan boundary.

GraphRAG's written answers have no code path: the CLI `query` command, the adapter's prose
`query`, the LlamaIndex `GraphRAGQueryEngine` wrapper, and the Neo4j bridge's prose
`query_findings` were removed, and a test asserts they stay absent. Generated index settings also
skip work V2 never reads: claim extraction is always disabled (no V2 component reads GraphRAG
covariates), text-unit vectors are not embedded (they serve only GraphRAG basic search), and local
search has no model assignment of its own (Local selection uses embeddings only). The DRIFT
`n_depth` and `concurrency` settings were removed because only the primer step runs.

Microsoft GraphRAG 2.6's upstream vector-store registry exposes LanceDB, Azure AI Search,
and Cosmos DB; it does not provide a Qdrant store. Cortex therefore does not instantiate the
upstream LanceDB store. `GraphRAGQdrantAdapter` is the required custom compatibility seam:
GraphRAG's canonical artifacts stay under the workspace root and the entity/report/text-unit
vectors are independently mirrored to Qdrant. Phase 7 will schedule actual index execution
and Phase 8 will connect these route adapters to the LlamaIndex router.

LanceDB remains a transitive installation in the GraphRAG worker image because Microsoft
GraphRAG 2.6 declares it as a package dependency. It is neither configured nor invoked by
Cortex; removing it would require forking or patching upstream GraphRAG and is outside the
supported compatibility boundary.

Phase 10 tests exercise deferred update snapshots, workspace-filtered mirroring, and the
separate Local, Global, and DRIFT route contracts without requiring a live provider.

## V1 query execution and settings

Every GraphRAG stage resolves its provider/model from the user-controlled stage setting and is
written to its own generated GraphRAG model entry; no execution model is substituted. Claim
extraction is optional and disabled by default. Community clustering is algorithmic, while the
community setting governs report generation.

Selected Local, Global, and DRIFT chat routes execute through the worker-owned workspace GraphRAG adapter.
The native GraphRAG answer is final and carries route/provider/model/duration metadata; the
regular Cortex synthesis worker skips it. Hybrid fallback is an explicit global policy and is off
by default. DRIFT has configurable conservative depth, follow-up, primer, concurrency, and
maximum-call limits. CLI usage fields unavailable from GraphRAG remain null in Cortex reports.
The native GraphRAG artifacts, Neo4j extracted layer, and Qdrant mirror coexist intentionally
during the staged V2 migration.

In Docker, the API never imports GraphRAG execution modules or invokes the GraphRAG CLI. It writes
a durable `QueryRun`, submits its ID through Redis/Dramatiq, and waits only for the configured
bounded chat window. The worker resolves persisted global settings, validates the workspace graph
root, executes the selected route, and writes the final answer, evidence, trace, and usage record
back to that query run. A worker failure or timeout is a controlled result; Hybrid fallback remains
an explicit policy. Cancellation is cooperative: a query already executing in GraphRAG cannot be
hard-interrupted by Dramatiq, but queued/timed-out work is marked terminal and never synthesized.
