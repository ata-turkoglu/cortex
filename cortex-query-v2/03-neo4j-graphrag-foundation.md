# Phase 03 — Neo4j-Backed Microsoft GraphRAG Foundation

## Goal

Add Neo4j as Cortex’s persistent/queryable knowledge graph and put Microsoft GraphRAG behind a Cortex-owned adapter boundary.

## Decisions

- No direct driver access outside the adapter.
- Raw/extracted and canonical layers are logically separate in one Neo4j database.
- GraphRAG extraction is a producer, not canonical truth.
- Retain Local, Global, and DRIFT; GraphRAG never owns final answers.

## Work

Neo4j runtime, config/secrets, health/readiness, workspace isolation, adapter contracts, Neo4j-backed GraphRAG integration, extracted and canonical namespaces, provenance-bearing extraction output, and a future EngineResult-compatible query contract.

## Acceptance

Neo4j starts correctly, isolation is tested, GraphRAG uses only the adapter path, and existing behavior does not regress.
