# Phase 14 — V2 Evaluation & Acceptance

## Goal

Build V2 correctness benchmarks beyond retrieval metrics.

Retain MRR, hit@k, recall@k, rank/baseline regression, citations, workspace isolation, and property safety. Add tests for query understanding/ambiguity, identity and false merges, alias/mention, enumeration, relation extraction/traversal, temporal and event/document dates, claim support/VerifiedFact/conflicts, exhaustive operations, completeness, multi-hop, graph+retrieval/GraphRAG composition, provenance, long-form grounding, conversation context, curation persistence, and generation isolation/readiness.

Use a precision-first bias: confidently wrong output is more severe than unsupported/ambiguous output, especially for merge, ownership facts, verified facts, exhaustive counts, and temporal relations. Define thresholds and bind them to CI/local validation.
