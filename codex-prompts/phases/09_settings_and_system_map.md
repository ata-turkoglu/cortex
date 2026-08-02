# Phase 9 — Settings and System Map

## Goal

Implement all global settings, runtime propagation, system health, system architecture map, and operational controls.

## Checklist

- [ ] Wire metadata extraction to the global layer-specific provider/model assignment.

- [ ] Implement Appearance Settings.
- [ ] Implement provider connection settings.
- [ ] Implement model discovery/listing where supported.
- [ ] Implement layer-specific model assignments.
- [ ] Implement capability validation.
- [ ] Implement embedding settings.
- [ ] Implement retrieval top-k settings.
- [ ] Implement reranker settings.
- [ ] Implement router confidence/multi-route thresholds.
- [ ] Implement GraphRAG pending threshold.
- [ ] Implement stage concurrency settings.
- [ ] Implement retry/backoff/timeouts.
- [ ] Implement retention settings.
- [ ] Implement batch-size settings.
- [ ] Implement health-check and SSE intervals.
- [ ] Implement conversation memory limits.
- [ ] Implement answer-style and grounding settings.
- [ ] Mark affected workspaces outdated/reindexing when index-dependent settings change.
- [ ] Implement static React Flow system map.
- [ ] Connect map nodes to real health checks.
- [ ] Implement node details with AInfo/AIcon.
- [ ] Implement header progress and active jobs drawer/dialog.
- [ ] Add settings validation tests.
- [ ] Update `IMPLEMENTATION_STATUS.md`.

## Acceptance criteria

- [ ] Operational thresholds are not hard-coded.
- [ ] Model incompatibilities are blocked in the UI and backend.
- [ ] Appearance changes apply globally.
- [ ] System-map statuses reflect backend health.

## Additional checklist

- [ ] Add upload-size and file-processing security settings.
- [ ] Add configurable pagination/page-size defaults.
- [ ] Add benchmark/diagnostic settings where appropriate.
- [ ] Expose recovery/interrupted job states in system/process maps.
- [ ] Expose reconciliation job status in diagnostics.

## Additional checklist — setup, defaults, budgets, and Ollama

- [ ] Implement first-run setup wizard.
- [ ] Implement OpenAI minimal-cost credential validation.
- [ ] Implement optional Ollama discovery and availability test.
- [ ] Show copyable Ollama pull commands without executing them.
- [ ] Add production-quality warning for small local models.
- [ ] Implement model assignment defaults and reset-to-default behavior.
- [ ] Implement daily/monthly budget settings and warnings.
- [ ] Implement GraphRAG automatic/manual/threshold controls.
- [ ] Implement estimated-cost confirmation settings.
- [ ] Add Windows data-path and connectivity diagnostics.

## Additional checklist — embedding settings

- [ ] Set Ollama `qwen3-embedding:0.6b` as the default selection.
- [ ] Show installed/missing status and model details.
- [ ] Show that changing embedding settings requires full dense reindexing.
- [ ] Require explicit confirmation before applying an embedding model/configuration change.
- [ ] Add configurable embedding batch size, timeout, keep-alive, and concurrency.
- [ ] Add an embedding benchmark/test action.
- [ ] Display dimensions, provider, model digest/version, health, and last benchmark.
