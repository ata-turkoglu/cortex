# Phase 09 — EngineResult & Result/Evidence Layer

## Goal

Unify all engine output under one typed contract and reconciliation layer.

## Invariant

No execution engine may directly author or persist the final user answer.

## Contract and acceptance

EngineResult carries structured rows/entities, graph paths, aggregates, text evidence, GraphRAG findings, claims/facts, provenance, completeness, confidence, ambiguity, conflicts, and trace. The layer normalizes, deduplicates/reconciles, preserves disagreement, validates provenance/completeness, ranks evidence, materializes citations, and returns a trustworthy reasoning package. Native GraphRAG prose cannot bypass it. Test answer ownership, exact citation traceability, and partial-failure visibility.
