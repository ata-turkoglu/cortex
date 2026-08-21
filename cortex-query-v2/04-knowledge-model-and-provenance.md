# Phase 04 — Canonical Knowledge Model, Identity & Provenance

## Goal

Create the first-class V2 knowledge model.

## Ontology

Stable upper types plus dynamic subtypes/properties/relations: Entity (Person, Organization, Location, Asset/Property), Document, LogicalDocument, Event, TemporalExpression, Claim, Evidence, and Fact.

## Identity and curation

Implement opaque stable IDs, original mentions, evidence-based resolution, conservative auto-merge, lossless merge/split history, aliases, and `extracted`, `validated`, `user_curated` authority with `user_curated > validated > extracted` precedence. Identity changes are lossless and provenance-aware. The UI supports merge, split, alias add/remove, evidence/mention inspection, and history.

## Claims, conflicts, and provenance

`ExtractedClaim → SupportedClaim → VerifiedFact`: confidence alone never verifies a fact; support requires evidence and verification needs an applicable validator. Retain conflicting claims and explicit conflict state.

Provenance: Workspace → Document → DocumentVersion → LogicalDocument → Chunk → exact source span, plus extraction run, provider/model, prompt/schema, confidence, validation state, generation, and source text.

## Acceptance

Test stable IDs, conservative merge, merge/split, curation precedence, conflicts, and exact-source provenance.
