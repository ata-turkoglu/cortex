# Query V2 repository boundaries

Status: **Phase 02 repository contract; runtime remains V1-equivalent**.

The V2 packages establish ownership and AI navigation before behavior moves. They intentionally do
not re-export V1 classes as V2 contracts: V1 `QueryPlan`, route selection, GraphRAG native answer,
and property aggregation do not satisfy the V2 IR/result invariants.

## Ownership tree

```text
backend/app/query/
  context/ understanding/ ir/ planning/ orchestration/
backend/app/knowledge/
  entities/ relations/ events/ temporal/ claims/ provenance/
backend/app/engines/
  structured/ graph/ hybrid/
backend/app/reasoning/
  research/ composition/
```

Every parent and child has canonical `AGENTS.md`, a generated thin `CLAUDE.md`, and a Python package
marker. Root → backend → parent → child navigation is recorded in `.ai/project-map.yaml` and
`docs/ai/index.md`.

## No-duplication mapping

| Concern | Active V1 owner | V2 owner / migration rule |
| --- | --- | --- |
| Query parsing, entity resolution, routes, answer orchestration | `app/chat/` | Move by later phases into `query/`; keep V1 imports stable until sharp cutover |
| Property-only exhaustive aggregation | `app/aggregation/property.py` | Preserve safety rules; general structured execution belongs to `engines/structured/` |
| Dense/BM25/fusion/reranking | `app/retrieval/` | Existing package remains the Retrieval Engine implementation; do not create `engines/retrieval/` |
| Microsoft GraphRAG adapter and artifacts | `app/graphrag/` | Existing package remains the GraphRAG Engine adapter; do not create `engines/graphrag/` |
| Durable jobs and checkpoints | `app/workflows/` | Reused by query/research/composition; workflow persistence is not copied |
| Canonical knowledge | none | New implementation belongs to `knowledge/` and the Cortex graph adapter |
| Canonical structured/graph execution | none | New implementation belongs to `engines/structured/` and `engines/graph/` |
| Cross-engine reconciliation | partial in `app/chat/` | New implementation belongs to `query/orchestration/` Result & Evidence boundary |
| Durable research/composition | none | New implementation belongs to `reasoning/` and reuses `app/workflows/` |

## Dependency direction

API and workflow entrypoints call query orchestration. Query Understanding produces IR without
engine imports. Execution Planning consumes IR and engine capability contracts. Engines may use
knowledge/retrieval/GraphRAG adapters and emit typed results, but cannot call the Answer Engine or
persist assistant prose. Reasoning consumes reconciled evidence packages. Lower layers never import
API modules.

During Phases 03–12, implementations move or are introduced only in their owning boundary, with
temporary compatibility imports kept at old public paths when tests or API modules still require
them. Compatibility wrappers must not become duplicate implementations and are removed at sharp
cutover.
