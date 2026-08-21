# Phase 10 — Structured Query & Knowledge Graph Engines

## Goal

Add deterministic/exhaustive structured queries and Neo4j graph traversal over canonical knowledge.

## Engines

Structured: enumeration, filters, distinct, count, group, rank, min/max, top-N, projection, and population comparison. Top-k retrieval is never exhaustive evidence.

Graph: canonical lookup, relation traversal, multi-hop, event participation, temporal constraints, provenance traversal, and conflict inspection. Neo4j access stays behind the Cortex adapter.

Prefer bounded uncertainty (`confirmed_count`, `unresolved_candidates`, `not_safely_enumerable`) to approximate counts. Test surname enumeration, generic count/list/group/rank, multi-hop, temporal graph, provenance, and unresolved entities.
