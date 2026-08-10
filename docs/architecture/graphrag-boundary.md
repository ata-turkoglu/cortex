# GraphRAG Boundary

Microsoft GraphRAG is canonical and exposed through a dedicated adapter with explicit
schemas and integration tests. NetworkX is secondary. Each workspace owns an isolated
GraphRAG root, while Qdrant resource types remain separate and every operation uses the
workspace filter.

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

`GraphRAGQueryEngine` wraps exactly one route as a LlamaIndex `CustomQueryEngine`. It preserves
the route identity, normalized evidence, workspace metadata, and citation labels as source nodes;
the Phase 8 router may select these engines but must not flatten them into a basic retriever.

When an upstream GraphRAG query fails after outputs exist, the adapter returns an unsupported
result with the explicit `graph_stale` fallback reason. This is a safe route-level signal for the
router to use Hybrid Search; it never presents stale graph output as grounded evidence.

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
The native GraphRAG artifacts and Qdrant mirror remain duplicated intentionally for V1.

In Docker, the API never imports GraphRAG execution modules or invokes the GraphRAG CLI. It writes
a durable `QueryRun`, submits its ID through Redis/Dramatiq, and waits only for the configured
bounded chat window. The worker resolves persisted global settings, validates the workspace graph
root, executes the selected route, and writes the final answer, evidence, trace, and usage record
back to that query run. A worker failure or timeout is a controlled result; Hybrid fallback remains
an explicit policy. Cancellation is cooperative: a query already executing in GraphRAG cannot be
hard-interrupted by Dramatiq, but queued/timed-out work is marked terminal and never synthesized.
