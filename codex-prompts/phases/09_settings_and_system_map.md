# Phase 9 — Settings and System Map

## Goal

Implement all global settings, runtime propagation, system health, system architecture map, and operational controls.

## Checklist

- [x] Wire metadata extraction to the global layer-specific provider/model assignment.

- [x] Implement Appearance Settings.
- [x] Implement provider connection settings.
- [x] Implement model discovery/listing where supported.
- [x] Implement layer-specific model assignments.
- [x] Implement capability validation.
- [x] Implement embedding settings.
- [x] Implement retrieval top-k settings.
- [x] Implement reranker settings.
- [x] Implement router confidence/multi-route thresholds.
- [x] Implement GraphRAG pending threshold.
- [x] Implement stage concurrency settings.
- [x] Implement retry/backoff/timeouts.
- [x] Implement retention settings.
- [x] Implement batch-size settings.
- [x] Implement health-check and SSE intervals.
- [x] Implement conversation memory limits.
- [x] Implement answer-style and grounding settings.
- [x] Mark affected workspaces outdated/reindexing when index-dependent settings change.
- [x] Implement static React Flow system map.
- [x] Connect map nodes to real health checks.
- [x] Implement node details with AInfo/AIcon.
- [x] Implement header progress and active jobs drawer/dialog.
- [x] Add settings validation tests.
- [x] Update `IMPLEMENTATION_STATUS.md`.

## Acceptance criteria

- [x] Operational thresholds are not hard-coded.
- [x] Model incompatibilities are blocked in the UI and backend.
- [x] Appearance changes apply globally.
- [x] System-map statuses reflect backend health.

## Additional checklist

- [x] Add upload-size and file-processing security settings.
- [x] Add configurable pagination/page-size defaults.
- [x] Add benchmark/diagnostic settings where appropriate.
- [x] Expose recovery/interrupted job states in system/process maps.
- [x] Expose reconciliation job status in diagnostics.

## Additional checklist — setup, defaults, budgets, and Ollama

- [x] Implement first-run setup wizard.
- [x] Implement OpenAI minimal-cost credential validation.
- [x] Implement optional Ollama discovery and availability test.
- [x] Show copyable Ollama pull commands without executing them.
- [x] Add production-quality warning for small local models.
- [x] Implement model assignment defaults and reset-to-default behavior.
- [x] Implement daily/monthly budget settings and warnings.
- [x] Implement GraphRAG automatic/manual/threshold controls.
- [x] Implement estimated-cost confirmation settings.
- [x] Add Windows data-path and connectivity diagnostics.

## Additional checklist — embedding settings

- [x] Set Ollama `qwen3-embedding:0.6b` as the default selection.
- [x] Show installed/missing status and model details.
- [x] Show that changing embedding settings requires full dense reindexing.
- [x] Require explicit confirmation before applying an embedding model/configuration change.
- [x] Add configurable embedding batch size, timeout, keep-alive, and concurrency.
- [x] Add an embedding benchmark/test action.
- [x] Display dimensions, provider, model digest/version, health, and last benchmark.
