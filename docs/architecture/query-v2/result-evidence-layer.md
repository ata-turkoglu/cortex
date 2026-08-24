# Query V2 Result & Evidence Layer

Status: **Active for the generation-bound retrieval path; reusable by later engine bridges.**

The Result & Evidence Layer is the mandatory convergence point between execution engines and
reasoning. Engines emit `EngineResult` schema version `1.0`; reconciliation emits
`ReasoningPackage` schema version `1.0`. Neither contract contains final-answer content or a
persistence operation.

## EngineResult

Every result is bound to one physical-plan step by workspace, step ID, engine, and capability. It
can carry structured rows, entities, graph paths, canonical events, aggregates, exact text evidence, GraphRAG
findings, claims or facts, provenance links, completeness, confidence, ambiguity, conflicts,
partial failures, and sanitized trace data.

Grounded items reference evidence declared in the same envelope. GraphRAG Local, Global, DRIFT,
or community prose is a finding only and requires the same evidence references as every other
material result. Unknown fields are rejected, so an engine cannot add a `final_answer` and bypass
the Answer Engine.

## Reconciliation

`reconcile_engine_results` accepts only detached values:

- a reconciliation contract derived from the physical plan;
- typed engine results; and
- trusted, workspace-scoped source snapshots loaded before reconciliation.

It performs no database, model, storage-adapter, or network call. It rejects crossed workspaces,
duplicate result/step identities, unsolicited steps, and engine/capability identities that differ
from the physical plan.

For semantic structured operations, the reconciliation contract admits only results corresponding
to final logical IR roots. An intermediate canonical scan or filter prerequisite is not
automatically a user-facing semantic result. This final-root rule prevents an exhaustive scan from
leaking into filtered LIST output while preserving its trace as an execution dependency.

For every evidence span, the layer verifies the complete document/version/logical-document/chunk
chain, generation, ordered offsets, and exact substring against the trusted chunk snapshot. Reuse
of one evidence ID for different spans invalidates every occurrence. Evidence with identical source
lineage and offsets is deduplicated, corroborating step identities are retained, and ranking uses
relevance, evidence quality, and independent step support. Citations are materialized only after
these checks and retain exact offsets and source text.

Compatible grounded results sharing a stable item identity are merged with their evidence.
Different grounded values for the same identity remain separate and produce an explicit conflict;
declared engine conflicts are also retained. Missing required steps and failed engines remain in
the reasoning package.

## Completeness and answer state

`corpus_complete` requires all required steps, an exhaustive boundary, one expected generation,
all candidates processed, all mandatory projections ready, sufficient validated sources, and no
failure or validation issue. Confidence cannot promote incomplete coverage. Grounded contracts may
return `partial` when allowed; a degraded contract that forbids partial results returns
`unsupported`. Ambiguity has priority over otherwise useful evidence.

## Live-runtime boundary

Production V2 invokes this layer after registry-dispatched retrieval, structured, canonical-graph,
and GraphRAG steps. Exact `graph.event_filter` results remain typed canonical events through
`EngineResult.events` and `ReasoningPackage.events`; their membership is never inferred from
retrieval. GraphRAG Local, Global, and DRIFT findings enter as `GraphRAGFinding` only after the
bridge resolves their complete source identity and content hash to a generation-bound trusted
chunk and exact full-chunk span. Unresolvable, cross-workspace, cross-generation, unknown, or
tampered references are rejected rather than silently omitted.
