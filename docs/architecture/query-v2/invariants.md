# Query V2 invariants

These invariants are binding for all Query V2 implementation phases.

1. No execution engine authors or persists the final user answer. Engines emit typed
   `EngineResult` values to the Result & Evidence Layer; only the Answer Engine owns final prose.
2. Every canonical knowledge assertion traces to workspace-scoped source evidence. The minimum
   chain is `Workspace → Document → DocumentVersion → LogicalDocument → Chunk → exact source span`.
3. `intent` is absent from V2 execution semantics. Query Understanding expresses meaning as typed
   operators; Execution Planning selects capabilities and engines separately.
4. Microsoft GraphRAG extraction is a producer of extracted knowledge and findings, never
   canonical truth. Local, Global, and DRIFT are execution capabilities, not intents.
5. Identity resolution is conservative, evidence-based, provenance-aware, and reversible.
   Stable opaque IDs, original mentions, aliases, merge/split history, and rejected candidates are
   preserved.
6. Knowledge precedence is `user_curated > validated > extracted`. Reindexing cannot erase or
   silently override user curation.
7. Claims advance only through explicit states: `ExtractedClaim → SupportedClaim → VerifiedFact`.
   Model confidence alone cannot produce a verified fact. Conflicting claims remain queryable and
   canonical knowledge may be `conflicted`.
8. Original temporal text, normalized value/range, precision, uncertainty, semantic role, and
   provenance are stored together.
9. Exhaustive count, list, grouping, ranking, min/max, top-N, and population comparison require a
   completeness contract. Top-k retrieval is never an exhaustive source.
10. Corpus completeness requires every mandatory projection for the same generation to be ready.
    Missing, stale, mixed-generation, or partially failed stages produce partial/unsupported state,
    not a complete answer.
11. Workspace isolation applies to relational state, Neo4j graph access, Qdrant, BM25, GraphRAG,
    files, caches, plans, evidence, and durable runs. Every adapter enforces the workspace boundary.
12. Existing property ownership and cadastral safeguards remain mandatory: label-bound fields,
    local entity/ownership spans, no inferred missing identifiers, and source-preserving claims.
13. Explicit ambiguity or unsupported output is safer than a confident wrong answer. Precision has
    priority over coverage, latency, and cost for identity merge, ownership, VerifiedFact,
    exhaustive results, and temporal relations.
14. Architecture changes update code, tests, owning documents, AI navigation, implementation
    status, and any affected `/system-map` representation together.

## Answer-state contract

- `grounded`: material claims have validated evidence, but no exhaustive coverage is implied.
- `corpus_complete`: the relevant population and all required same-generation projections were
  enumerated successfully under the declared workspace/time/filter boundary.
- `partial`: useful supported material exists, but an engine, projection, generation, ambiguity, or
  coverage requirement prevents a complete result.
- `unsupported`: the available evidence cannot support the requested conclusion.
- `ambiguous`: materially different interpretations or identities remain unresolved and answering
  one silently would be unsafe.

Completeness and confidence are independent. High confidence cannot promote partial coverage to
`corpus_complete`.
