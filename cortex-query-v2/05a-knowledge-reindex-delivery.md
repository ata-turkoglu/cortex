# Phase 05A — Knowledge Reindex Delivery

## Purpose

Finish the production `knowledge_reindex` workflow before starting Query V2 Phase 06.

## Completed foundations

- [x] Candidate generation and all eleven readiness checkpoints.
- [x] Source snapshot fingerprinting, mismatch rejection, and failure-safe activation.
- [x] Strict provider JSON decoding and exact-span/provenance validation.
- [x] Provider extraction adapter, typed construction, and canonical entity/relation/event/temporal/claim promotion boundaries.
- [x] Generation-bound BM25/Qdrant and GraphRAG projection adapters.
- [x] Durable workflow definition, API/schema visibility, workspace index lock, and fail-closed stage executor.

## Required delivery work

1. Persist a `KnowledgeReindexRunContext` keyed by workflow run and candidate generation.
   It must store snapshot identity, extraction output references, mention-to-canonical mappings,
   projection fingerprints, and safe retry checkpoints without storing source text or secrets.
2. Implement the specialized Dramatiq executor and register it in the worker.
   It claims the `knowledge_reindex` lock, runs external/model calls outside SQLite transactions,
   mirrors workflow-step and generation-stage transitions, and releases the lock on every terminal state.
3. Complete conservative identity resolution against existing canonical entities.
   Resolve only unique exact-name matches corroborated by two document versions; preserve unresolved
   candidates and never create a silent merge.
4. Persist canonical relations, events, temporals, and claims with full document/version/logical
   document/chunk evidence chains and canonical endpoint links.
5. Bind the real BM25/Qdrant rebuild and GraphRAG build to the candidate generation.
   GraphRAG sync must receive the candidate generation, and a stale/mismatched output must fail the run.
6. Add a generation-readiness API/read model and show active/candidate/failed generation state in the UI.
7. Run acceptance: end-to-end indexing, retry/idempotency, generation mismatch, mandatory failure,
   curation preservation, workspace isolation, and opt-in live Neo4j/GraphRAG validation.

## Exit criteria

`knowledge_reindex` completes a real workspace run without manual intervention; all mandatory
stages are ready for one generation; only then is the candidate activated. Phase 06 starts only
after this contract and its acceptance suite pass.

## Delivered — 2026-08-18

The specialized Dramatiq path now registers a concrete executor for every mandatory stage,
resumes one immutable candidate through per-chunk extraction artifacts, and performs provider and
store work outside SQLite transactions. Strict OpenAI Structured Outputs are aligned only to exact
literal source occurrences; assertions that remain non-literal after bounded repair are rejected,
not promoted. Conservative identity, canonical typed knowledge, generation-scoped BM25/Qdrant,
Microsoft GraphRAG, readiness API/UI, retry, mismatch, isolation, and live Neo4j acceptance are
covered.

Live acceptance activated generation `8d4665b6-7426-4abd-a95a-6df02cddc20a` for the selected
19-chunk workspace only after all eleven stages became ready. This is a Phase 05A knowledge
generation acceptance result, not the Query V2 runtime cutover or a claim that every workspace has
been rebuilt. Phase 13 still owns the full-corpus rebuild and sharp activation.
