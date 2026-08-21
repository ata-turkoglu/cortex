# Phase 11 — Reasoning, Research & Composition

## Goal

Make Cortex a general-purpose conversational research assistant over the workspace, not only a query/RAG system.

Simple counts are queries; a request to write a ten-chapter book from the archive is not one Query IR.

## Durable runs and acceptance

Use ResearchRun and CompositionRun with checkpoints, subqueries, evidence collections, outline, chapter/section state, and validation state, reusing workflow infrastructure where practical.

```text
research goal → decomposition → multiple Query IRs → plans → evidence → cross-source reasoning
→ outline → composition → grounding/consistency checks → final artifact
```

Preserve paragraph/sentence internal provenance. Test multi-step resume/recovery, evidence lineage, and long-form grounding.
