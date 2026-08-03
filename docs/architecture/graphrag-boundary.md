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

`GraphRAGInputMaterializer` copies only active normalized document versions from one workspace
into that workspace's GraphRAG `input` root. It validates every normalized path against the
configured data root and does not read another workspace's rows. Worker code can materialize this
manifest before a deferred index/update execution without holding a database transaction open.

`GraphRAGAdapter.initialize()` invokes the supported GraphRAG `init` command only for that
workspace root and records the resulting `settings.yaml` for the later worker-owned index call.
It does not configure or reveal provider secrets.

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
