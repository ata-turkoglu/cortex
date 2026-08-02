# Phase 8 — Chat and Query

## Goal

Implement workspace-scoped conversations, LlamaIndex Router, query workflows, response synthesis, citations, memory summarization, and query debugging.

## Checklist

- [ ] Implement workspace-scoped conversations.
- [ ] Implement messages and message status.
- [ ] Implement query workflow.
- [ ] Implement LlamaIndex Router.
- [ ] Add route descriptions and selector behavior.
- [ ] Support single-route selection.
- [ ] Support approved multi-route selection.
- [ ] Implement safe fallback to Hybrid Search.
- [ ] Store selected route, reason, and confidence.
- [ ] Implement answer generation through assigned provider/model.
- [ ] Implement response synthesis.
- [ ] Implement evidence-backed citations.
- [ ] Implement source details dialog.
- [ ] Implement conversation memory window.
- [ ] Implement conversation summary through assigned model.
- [ ] Implement Automatic, Document Search, and Deep Analysis modes.
- [ ] Implement answer style settings.
- [ ] Implement external-knowledge-off behavior.
- [ ] Implement inference labeling.
- [ ] Implement message edit behavior.
- [ ] Implement query debug/process map.
- [ ] Add route and citation tests.
- [ ] Update `IMPLEMENTATION_STATUS.md`.

## Acceptance criteria

- [ ] Conversations never cross workspace boundaries.
- [ ] Route choice is visible in debug details.
- [ ] Unsupported answers do not fabricate evidence.
- [ ] Citations open the correct document version and evidence.

## Additional checklist

- [ ] Use generated OpenAPI client and types in all chat/query frontend features.
- [ ] Add query-latency benchmark capture.
- [ ] Add pagination/virtualization for large conversation histories where needed.

## Additional checklist — default model and cost behavior

- [ ] Seed Query Router, Conversation Summary, Query Expansion, and Answer Generation with `gpt-5.6-luna`.
- [ ] Disable Query Expansion by default.
- [ ] Disable automatic expensive-model escalation by default.
- [ ] Display query token usage and estimated cost in technical details.
- [ ] Enforce soft-budget behavior for queued cost-incurring work.
