# Query V2 execution planning

Status: **Phase 08 planning plus dormant Phase 13 dense and sparse execution reads; V1 remains active**.

Execution Planning consumes a semantically validated `LogicalQueryIR` and a detached,
workspace-scoped readiness snapshot. It performs no database access and invokes no model, storage,
or execution engine. The output is `PhysicalExecutionPlan` schema version `1.0`.

## Physical plan contract

A ready plan is a typed acyclic graph. Every `ExecutionStep` declares:

- the selected engine capability and logical-node trace;
- dependencies plus logical input and output types;
- workspace, active-generation, and mandatory-projection readiness preconditions;
- grounded or exhaustive coverage expectation; and
- fail-closed or partial failure behavior with correctness- and coverage-preserving fallbacks.

Every executable graph ends at `evidence.reconcile_and_validate`. This is a planning contract for
the Phase 09 Result & Evidence boundary; Phase 08 does not implement execution or final answer
composition.

The planner retains unresolved interpretations and produces separate candidate physical DAGs for
ambiguity. A candidate that cannot satisfy readiness is not silently converted into another
meaning. If fewer than two executable candidates remain, the result is unsupported rather than a
guessed interpretation.

## Capability selection

Capabilities are declarations, not a static route taxonomy. Built-in declarations cover canonical
enumeration and structured operators, graph resolution/traversal/multi-hop/temporal and
contradiction analysis, hybrid and semantic evidence retrieval, GraphRAG Local/Global/DRIFT and
community context, evidence synthesis, long-form research, and final reconciliation.

Selection is lexicographic in this fixed order:

1. correctness;
2. evidence quality;
3. coverage quality;
4. reasoning quality;
5. latency; and
6. cost.

Cost therefore cannot displace a higher-quality plan. Grounded retrieval may use an explicitly
declared weaker capability and retain partial-result semantics. Exhaustive work cannot fall back to
grounded retrieval, use stale readiness, cross workspaces, or mix generations. Missing readiness,
active generation, or required projections makes the plan unsupported.

## Activation boundary

The implementation lives in `backend/app/query/planning/` and is not connected to `app/chat/`.
V1 query parsing, route selection, execution, and final-answer behavior remain unchanged. This
phase does not claim a V2 indexing cutover, successful production engine execution, readiness UI,
or corpus completeness. The current-state `/system-map` records the dormant executor boundary but
does not represent it as a live answer path.

Phase 13 adds the internal-only app/query/execution.py skeleton beneath an existing physical plan.
It resolves one immutable GenerationScope at execution start, then passes it unchanged to planned
generation-bound reads:

    Physical plan -> V2 executor -> immutable GenerationScope
                                        -> dense adapter -> Qdrant workspace + generation + embedding filter
                                        -> sparse adapter -> knowledge-candidates/<generation>/bm25

The dense adapter uses a Qdrant filter requiring workspace, generation, and embedding identity.
The sparse adapter loads only the candidate-owned BM25 artifact, validates its workspace and
generation metadata, and has no legacy workspace BM25 fallback. Neither adapter re-resolves scope.

The skeleton returns separate dense and sparse internal evidence plus an in-memory trace with
resolved workspace, generation, embedding hash, physical engine, result counts, and a logical
generation BM25 artifact identity. Fusion, result/provenance reconciliation, Answer Engine
rendering, user-facing chat, and runtime activation remain outside this batch.
