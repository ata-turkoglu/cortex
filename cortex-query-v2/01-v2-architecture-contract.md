# Phase 01 — V2 Architecture Contract

## Goal

Freeze the V2 target architecture as binding documentation without changing runtime behavior.

## Work

Create or update canonical documentation for Conversation Context, Query Understanding, Logical Query IR, Execution Planning, Structured Query Engine, Knowledge Graph Engine, Retrieval Engine, GraphRAG Engine, Result & Evidence Layer, Reasoning & Composition, Answer Engine, Indexing V2 / Knowledge Construction, and V2 invariants.

## Required invariants

1. No execution engine authors or persists a final answer.
2. Engines return typed results to the Result & Evidence Layer.
3. Canonical assertions require source-evidence provenance.
4. `intent` is absent from V2 execution semantics.
5. Semantic interpretation and physical engine selection are separate.
6. GraphRAG extraction is not canonical truth.
7. Identity is conservative and provenance-aware; original mentions remain preserved.
8. Reindexing cannot overwrite user curation.
9. Confidently wrong output is worse than explicit ambiguity or unsupported output.
10. Exhaustive answers require completeness and workspace isolation.
11. Preserve property ownership/cadastral safety rules.
12. Architecture changes update code, docs, System Map, and AI context together.

## Acceptance

- Separate V1 current-state and V2 target docs.
- Preserve production runtime behavior.
- Pass context and documentation validation.
