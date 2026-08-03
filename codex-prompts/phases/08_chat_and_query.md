# Phase 8 — Chat and Query

## Goal

Implement workspace-scoped conversations, LlamaIndex Router, query workflows, response synthesis, citations, memory summarization, and query debugging.

## Checklist

- [x] Implement workspace-scoped conversations.
- [x] Implement messages and message status.
- [x] Implement query workflow.
- [x] Implement LlamaIndex Router.
- [x] Add route descriptions and selector behavior.
- [x] Support single-route selection.
- [x] Support approved multi-route selection.
- [x] Implement safe fallback to Hybrid Search.
- [x] Store selected route, reason, and confidence.
- [x] Implement answer generation through assigned provider/model.
- [x] Implement response synthesis.
- [x] Implement evidence-backed citations.
- [x] Implement source details dialog.
- [x] Implement conversation memory window.
- [x] Implement conversation summary through assigned model.
- [x] Implement Automatic, Document Search, and Deep Analysis modes.
- [x] Implement answer style settings.
- [x] Implement external-knowledge-off behavior.
- [x] Implement inference labeling.
- [x] Implement message edit behavior.
- [x] Implement query debug/process map.
- [x] Add route and citation tests.
- [x] Update `IMPLEMENTATION_STATUS.md`.

## Acceptance criteria

- [x] Conversations never cross workspace boundaries.
- [x] Route choice is visible in debug details.
- [x] Unsupported answers do not fabricate evidence.
- [x] Citations open the correct document version and evidence.

## Additional checklist

- [x] Use generated OpenAPI client and types in all chat/query frontend features.
- [x] Add query-latency benchmark capture.
- [x] Add pagination/virtualization for large conversation histories where needed.

## Additional checklist — default model and cost behavior

- [x] Seed Query Router, Conversation Summary, Query Expansion, and Answer Generation with `gpt-5.6-luna`.
- [x] Disable Query Expansion by default.
- [x] Disable automatic expensive-model escalation by default.
- [x] Display query token usage and estimated cost in technical details.
- [x] Enforce soft-budget behavior for queued cost-incurring work.
