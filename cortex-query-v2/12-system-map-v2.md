# Phase 12 — System Map V2

## Goal

Make `/system-map` the actual runtime architecture manifest.

## Groups

Query: Conversation Context, Query Understanding, Query IR, Execution Planning, Structured Query, Knowledge Graph, Retrieval, GraphRAG, Result & Evidence, Reasoning & Composition, Answer.

Indexing: Source Processing, Document Structure, Entity/Mention, Identity, Relation, Event, Temporal, Claim/Fact, KG Build, BM25, Dense/Qdrant, GraphRAG, Generation/Readiness.

Each React Flow group maps to a real subsystem boundary, canonical docs, and relevant AGENTS/CLAUDE context. Remove stale V1 flow, show GraphRAG/canonical KG separation, common Result & Evidence convergence, and the separate Execution Planning parent.
