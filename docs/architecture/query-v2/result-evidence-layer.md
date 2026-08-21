# Query V2 Result & Evidence Layer

Status: **Phase 09 implemented behind the inactive V2 boundary**.

The Result & Evidence Layer is the mandatory convergence point between execution engines and
reasoning. Engines emit `EngineResult` schema version `1.0`; reconciliation emits
`ReasoningPackage` schema version `1.0`. Neither contract contains final-answer content or a
persistence operation.

## EngineResult

Every result is bound to one physical-plan step by workspace, step ID, engine, and capability. It
can carry structured rows, entities, graph paths, aggregates, exact text evidence, GraphRAG
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

## Activation boundary

Phase 09 defines normalization and reconciliation only. Phase 10 engines will produce this
contract, and later phases own execution, reasoning, and the Answer Engine. V1 chat and its current
citations remain unchanged. No V2 indexing cutover, production engine run, readiness UI, or corpus
completeness is claimed, so the current-state `/system-map` remains unchanged.
