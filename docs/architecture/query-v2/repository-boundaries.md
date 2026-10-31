# Query V2 repository boundaries

Status: **active V2 ownership contract.**

The V2 packages own production chat. Historical V1 `QueryPlan`, route selection, GraphRAG native
answer, and property aggregation do not satisfy V2 IR/result invariants and are not production
dependencies.

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

| Concern | Current V2 owner | Historical / compatibility note |
| --- | --- | --- |
| Production query runtime, planning, reconciliation, answer persistence | `app/query/` | The V1 `app/chat/` orchestration has been removed |
| Structured canonical execution | `app/engines/structured/` | The V1 `app/aggregation/property.py` has been removed |
| Dense/BM25/fusion/reranking | `app/retrieval/` | Existing package remains the V2 Retrieval Engine adapter; do not create `engines/retrieval/` |
| Microsoft GraphRAG adapter and artifacts | `app/graphrag/` | Existing package remains the V2 GraphRAG adapter; do not create `engines/graphrag/` |
| Durable jobs and checkpoints | `app/workflows/` | Reused by query/research/composition; workflow persistence is not copied |
| Canonical knowledge | `app/knowledge/` and graph adapter | Incomplete / blocked; do not describe Neo4j as proven durable canonical truth |
| Canonical structured/graph execution | `app/engines/structured/` and `app/engines/graph/` | Not production accepted |
| Cross-engine reconciliation | `app/query/orchestration/` | V1 evidence helpers are historical only |
| Durable research/composition | `app/reasoning/` | Reuses `app/workflows/` |

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
