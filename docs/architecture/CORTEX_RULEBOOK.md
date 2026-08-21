# Cortex Architecture Rulebook

Read this rulebook before changing query planning, routing, retrieval, evidence selection,
aggregation, normalization, citations, or answer generation. Binding V1 decisions remain in
`codex-prompts/docs/DECISIONS.md`.

## Query and aggregation invariants

- Aggregation is an opt-in execution route. Names, property vocabulary, entities, or document
  types alone never select it.
- General identify, describe, timeline, broad archive, document lookup, and evidence-based QA
  retain their existing routes. A property description is not an inventory.
- Only explicit exhaustive inventory, grouping, deduplication, total, or count semantics select
  aggregation. Verified counts must not be derived from top-k semantic retrieval.
- Exhaustive operations are workspace-scoped and report candidate/processed source counts and
  completion state. They never claim external or current-world completeness.
- Chunks are evidence, not records. Property aggregation is candidate evidence → typed claims →
  normalized property identities and ownership claims → deduplicated records → answer.
- Normalized records preserve document, version, chunk, and citation provenance. Original values
  are retained alongside normalized values; missing cadastral fields are never fabricated.
- Property identity uses only known province, district, neighborhood, pafta, ada, parcel, and
  independent-section components. Similar descriptions alone never justify a merge.
- Cadastral fields are label-bound: missing pafta, ada, parsel, or independent-section values
  remain null and are never inferred by shifting adjacent numbers. Renderers display only validated
  known fields and never emit dangling phrases such as `nolu parsel` or `sayılı parsel`.
- Do not hardcode people, document IDs, parcel IDs, or production totals outside tests.
- Debug metadata records workspace identity, deterministic route reason codes, and completion.
- Describe answers synthesize the most informative supported facts from selected evidence rather
  than collapsing rich evidence into generic category labels. The final answer markers, citation
  payload, source cards, and user-visible source count all derive from one validated final set.
- A slash fraction is an ownership share only with bounded nearby ownership context and a local
  structural association to the resolved entity. Legal identifiers, dates, document numbers, and
  unknown fractions are never rendered as shares.
- Entity-specific property facts require a direct local ownership span for the resolved person;
  family/heir context and whole-chunk co-occurrence are not ownership evidence. Collapsed OCR
  ownership lists are segmented into individual share/person items before binding.

## Documentation rule

Architecture changes update the owning document and its pipeline diagram in the same change.
Any architectural change affecting a process represented on `/system-map` updates the corresponding
React Flow diagram and linked architecture Markdown in the same change. Any project-level behavior
summarized in `docs/chatgpt-context/` updates the affected context file in the same change; unrelated
context files do not need mechanical updates.
