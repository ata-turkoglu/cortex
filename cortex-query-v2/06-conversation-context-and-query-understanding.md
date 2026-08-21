# Phase 06 — Conversation Context & Semantic Query Understanding

## Goal

Replace regex-centric V1 interpretation with a conversation-aware semantic planner.

## Context

Follow-ups such as “What do we know about Hasan Tahsin Merter?” then “What about the children?” must resolve as `children_of(conversation.last_resolved_entity)`. Conversation-local assumptions never mutate the canonical KG.

## Planner and acceptance

Use an LLM-backed planner with configurable simple/standard/complex tiers, quality-first escalation, candidate interpretations/plans, schema-constrained output, unresolved/ambiguous states, and no `intent` output. Distinguish event/document/mentioned dates, ranges, before/after relations, and approximate/partial dates. Test follow-up references, carry-over, ambiguity, temporal meaning, tier selection, and escalation.

## Delivery status

- [x] Durable, versioned conversation-local context with workspace/conversation isolation, bounded
  history snapshots, source-message validation, and optimistic revisions.
- [x] Versioned semantic-understanding schema with typed entities, targets, relations, operators,
  coverage, candidates, ambiguity/unresolved states, and no V2 `intent` or engine selection.
- [x] Configurable simple/standard/complex semantic planner with strict provider JSON Schema output,
  bounded repair, confidence/state escalation, and detached provider-call inputs.
- [x] Event/document/mentioned, range, before/after, approximate, and partial temporal semantics plus
  deterministic follow-up entity and temporal-focus carry-over.
- [x] Focused migration/isolation/schema/planner/carry-over/V1 regression tests, generated OpenAPI
  client, architecture/context documentation, and System Map non-cutover review.

Phase 06 is implemented but remains disconnected from the active V1 chat entrypoint until the sharp
cutover phase. Phase 05A production delivery remains deferred and incomplete; this phase does not
claim an indexing cutover or corpus completeness.
