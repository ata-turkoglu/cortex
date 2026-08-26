# Canonical Core V2: Minimal Canonical Design

> **Status: IMPLEMENTED, ACCEPTANCE INCOMPLETE — not production accepted.** SQLite authority,
> manifest-backed construction, durable mention/decision/membership/status accounting, governed
> surname projection, conservative Property/ownership writes, and the SQLite structured reader are
> implemented. Focused construction tests pass, but the full adversarial, isolation, and V2 E2E
> acceptance suite has not yet passed. `canonical.exhaustive` is therefore still partial and
> `canonical.graph` remains unavailable.

## Scope and decisions

The first capability is an exhaustive answer to: “Merter soyadlı kişileri listele,
her biri için belgelerde geçen taşınmaz sayısını belirt ve en fazla taşınmaz kaydı
olan kişiden en aza doğru sırala.” The count is a distinct count of safe, document-supported
canonical Properties; it is not a statement of current legal ownership.

The existing capability separation is preserved: `retrieval.grounded` and
`graphrag.grounded` stay independent; `canonical.exhaustive` and `canonical.graph`
stay separately readiness-gated. This design does not alter Qdrant, BM25, the immutable
source manifest, source/evidence validation, reconciliation, `ReasoningPackage`, workflow
recovery, embedding runtime, or the V2 query path.

| Topic | Proposed decision |
| --- | --- |
| Durable authority | New relational tables in existing Cortex SQLite. |
| Canonical ID | Application-generated UUIDv7 text ID, opaque/stable and never based on a name, document, generation, Neo4j ID, or GraphRAG ID. UUIDv4 is an acceptable temporary fallback. |
| Identity | Workspace-scoped, generation-independent Person. Each mention has one durable `NEW`, `LINK`, or `UNRESOLVED` decision. |
| Alias | Derived from accepted mention links; no separate alias lifecycle in Minimal Core. |
| Property | Conservative, label-bound cadastral identity; incomplete references are not deduplicated. |
| Relation | Direct-evidence `document_supported_ownership`, not present-world ownership truth. |
| Structured read authority | SQLite generation projection. |
| Neo4j | Rebuildable projection only; `canonical.graph` may remain unavailable for phase one. |

SQLite is recommended because Cortex already uses it as transactional relational authority with
foreign keys, uniqueness, migrations, WAL, and short transactions. The current Neo4j prototype
mixes identity, evidence, lifecycle, and read projection, so it must not be the sole authority.

## Authority matrix

| Concept | Authority | Generation-scoped | Durable | Rebuildable |
| --- | --- | ---: | ---: | ---: |
| Source/version/chunk | Existing SQLite source model + immutable manifest | membership | yes | projections only |
| Mention | `entity_mentions` | yes | yes | idempotent re-extraction |
| Identity decision | `identity_decisions` | evidence context | yes | no |
| Canonical Person | `canonical_entities` | no | yes | no |
| Alias | Derived accepted mentions | read in G | indirect | yes |
| Property | `canonical_properties` | no | yes | no |
| Ownership assertion | `ownership_assertions` | yes | yes | generation projection |
| Generation membership/status | SQLite projection/status tables | yes | yes | yes |
| Neo4j nodes/edges | Neo4j | yes | no | yes |
| Qdrant/BM25/GraphRAG | Existing generation artifacts | yes | artifact | yes |

## Relational schema

All IDs are text UUIDs; every service enforces workspace scope for every foreign key.

```text
canonical_entities
  id PK, workspace_id FK, entity_type CHECK ('person'), preferred_name,
  normalized_preferred_name, created_at, updated_at
  UNIQUE(workspace_id,id); INDEX(workspace_id,entity_type,normalized_preferred_name)

entity_mentions
  id PK, workspace_id, generation_id FK knowledge_generations, entity_type CHECK
  ('person','asset_property'), surface_text, normalized_text, document_id,
  document_version_id, logical_document_id, chunk_id, span_start, span_end,
  source_text, source_text_hash, extraction_type, extractor_version, created_at
  UNIQUE(workspace_id,generation_id,chunk_id,span_start,span_end,entity_type,extraction_type)
  INDEX(workspace_id,generation_id,entity_type,normalized_text)

identity_decisions
  id PK, workspace_id, mention_id FK entity_mentions, decision CHECK
  ('NEW','LINK','UNRESOLVED'), canonical_entity_id FK canonical_entities NULL,
  decision_basis_json, candidate_entity_ids_json, resolver_version, policy_version, created_at
  UNIQUE(workspace_id,mention_id)
  CHECK NEW/LINK => non-null entity; UNRESOLVED => null entity

canonical_properties
  id PK, workspace_id, property_kind CHECK ('real_property'), province, district,
  neighborhood, pafta, ada, parsel, independent_section (all nullable), identity_key,
  identity_strength CHECK ('strong'), created_at
  UNIQUE(workspace_id,identity_key)

ownership_assertions
  id PK, workspace_id, generation_id, person_id FK canonical_entities,
  property_id FK canonical_properties, relation_type CHECK ('document_supported_ownership'),
  person_mention_id FK entity_mentions, property_mention_id FK entity_mentions,
  document/version/logical-document/chunk IDs, exact span/text/hash, optional bound share/date,
  assertion_rule_version, created_at
  UNIQUE(workspace_id,generation_id,person_mention_id,property_mention_id,relation_type)
  INDEX(workspace_id,generation_id,person_id,property_id)

generation_canonical_memberships
  workspace_id,generation_id,canonical_entity_id PK, entity_type,
  membership_basis_mention_id,created_at
  UNIQUE(workspace_id,generation_id,membership_basis_mention_id)

canonical_generation_status
  workspace_id,generation_id,projection_version PK, status CHECK
  ('UNAVAILABLE','BUILDING','READY','PARTIAL','FAILED'), manifest_hash,
  manifest_chunk_count,processed_chunk_count,mention_count,resolved_mention_count,
  unresolved_mention_count,safe_property_count,assertion_count,rejected_assertion_count,
  failed_chunk_count,projection_row_count,failure_reason_json,completed_at,updated_at
```

`entity_mentions` is idempotent by exact source location/type, not text. Every write first validates
the span, hash, document/version/logical-document/chunk identity, and immutable-manifest membership.
The decision ledger is authoritative; its basis/candidates/resolver version are diagnostic. It does
not copy generation ownership onto the Person.

A safe Property key requires labeled `province + district + neighborhood + ada + parsel`, with
independent section included when present and pafta included when supplied. Missing fields stay null;
numbers never shift fields. Weaker evidence remains an unresolved property mention: it creates no
Property or countable ownership assertion. A fraction is only a share if local syntax binds it to
that person and ownership assertion.

## Identity, generation, and build policy

```text
validated Person mention -> deterministic resolver -> NEW | LINK | UNRESOLVED
```

Same name, surname, document/chunk co-occurrence, shared property, GraphRAG similarity, and embedding
similarity are never sufficient to link. `LINK` needs one unique candidate and a versioned,
deterministic evidence rule. One-token, initial, surname-only, malformed-OCR, and ambiguous mentions
are `UNRESOLVED`. Accepted mention surface forms derive aliases with their mention/decision IDs as
basis. No alias scoring, merge, split, supersession, or lifecycle API is introduced.

Production extraction may carry `identity_candidates` only on a Person mention: stable SQLite
canonical Person IDs plus non-empty `candidate_provenance`. Construction validates each candidate in
SQLite for workspace and Person type, records the provenance in the existing decision basis, and
passes the IDs to the centralized conservative resolver. Unknown, cross-workspace, wrong-type, or
multiple candidates fail closed; candidate presence never authorizes name-based linking.

A Person belongs to G if at least one G Person mention has `NEW` or `LINK`; use the lowest mention
ID as deterministic membership basis while preserving all evidence. Absence from G deletes only G’s
replaceable membership row, never a Person/mention/decision/property/assertion history row.

`surname` is a governed, generation projection from an accepted complete-name mention plus the exact
surname substring—not mutable `preferred_name` at query time. Normalize NFKC, Turkish dotted/dotless-I,
case, whitespace, and punctuation boundaries. Withhold multi-part surnames until approved parser
policy; do not invent OCR variants.

```text
Immutable manifest -> exact-span mentions -> identity ledger -> safe Properties + direct assertions
  -> G membership + surname projection -> completeness -> optional Neo4j materialization
```

Build in manifest order. Extractor/resolver/model work is detached; SQLite writes are short batched
upserts. A retry must return the identical row/decision or fail on conflicting payload. Replace only
the explicitly scoped G read projection transactionally. Neo4j builds from SQLite in a separate,
idempotent step; its failure never destroys SQLite authority.

## Completeness and read path

`UNAVAILABLE` means no validated projection, `BUILDING` means no reads, `FAILED` means a
manifest/span/constraint error, and `PARTIAL` means all chunks completed but unresolved identity,
property, or ownership evidence could affect the count. Partial must not be advertised as exhaustive.

`canonical.exhaustive` is READY only when the exact active generation/version has: matching manifest
hash/count; every chunk processed once with no failures; every evidence row manifest/span-valid;
one decision per Person mention with no population-affecting unresolved identity; every potentially
countable property safely resolved or causing PARTIAL; membership equal to all accepted people
including zero-property people; non-conflicting governed surname values; and projection counts/
fingerprint matching durable rows. This is independent of retrieval capability readiness.

`canonical.graph` is READY only if exhaustive is READY and Neo4j has an exact-version projection
with matching workspace/generation/membership/property/assertion/evidence fingerprint. It should
remain unavailable in the first milestone; an internal SQL relation is not general graph traversal.

```text
SemanticUnderstanding -> LogicalQueryIR Scan(Person exhaustive)
 -> Filter(governed surname='Merter') -> RelationAggregate(COUNT DISTINCT property_id)
 -> Rank(property_count DESC, preferred_name ASC, canonical_entity_id ASC)
 -> SQLite G membership LEFT JOIN G ownership assertions -> EngineResult
 -> reconciliation + manifest validation -> ReasoningPackage -> AnswerEngine
```

The left join retains zero-count people. Multiple documents for one safe Property count once. Rows
carry membership/identity evidence and every counted assertion’s exact provenance. Query execution
is read-only: it cannot create identities, resolve uncertainty, extract, repair, or mutate.

## Migration, acceptance, and follow-up

### Current implementation status

Implemented in migration `0022_minimal_canonical_core`: the seven SQLite authority tables,
UUIDv7 helper, idempotent exact Person mentions, durable `NEW`/`LINK`/`UNRESOLVED` decisions,
generation membership rebuild, completeness status calculation, and a deterministic read-only
SQLite ranking helper. The readiness snapshot now accepts only a `READY` SQLite completeness
record for `canonical.exhaustive`; `canonical.graph` is explicitly unavailable.

Implemented after migrations `0022`/`0023`: manifest-backed production construction writes,
safe Property/ownership construction, governed persisted surname projection, and injection of the
SQLite reader into the production structured engine. Migration `0024` persists per-manifest-chunk
accounting. No existing user generation was rebuilt or made canonical-ready.

Acceptance is intentionally incomplete: only focused manifest-backed construction/read tests have
passed. Same-name/ambiguous identity adversaries, workspace/generation isolation, retry/failure,
Neo4j-unavailable structured queries, no-fallback telemetry, and the full V2 target-query path
remain gates before production acceptance.

Migration is additive: add the SQLite schema/builder under a projection version, then reconstruct
the first clean core from immutable source using this conservative policy. Existing Neo4j data is
non-authoritative and must not be automatically reused; preserve it for compatibility/audit. Only
after SQLite acceptance materialize replaceable Neo4j rows. This design creates no generation and
does not reindex/rebuild the corpus.

The deterministic fixture contains: Ayşe Merter/P1 repeated in two documents; Mehmet Merter/P2+P3;
Zeynep Merter/zero property; ambiguous same/near-name Ayşe; a non-ownership co-occurrence; and an
explicit ownership phrase with incomplete Property identity. Expected accepted ranking is Mehmet 2,
Ayşe 1, Zeynep 0. Assert exact spans/hashes, manifest counters, P1 deduplication, zero retention,
ordering, and readiness. Adversarial tests cover same/different names, surname-only/OCR/alias,
cross-workspace/generation, similar/missing parcels, unbound fractions, historical transfer wording,
retry/resume/projection rebuild/manifest tamper, unavailable/partial queries, and no retrieval fallback.

Implementation must update this document’s status, implementation status, Query V2 construction/
engine/runtime docs, docs index, relevant chat context, any public API contract, migrations, and
`/system-map`. Proposed map:

```text
Source Manifest -> Canonical Extraction -> Mentions + Assertions -> Identity Ledger
 -> Durable SQLite Canonical Store -> G Projection + Completeness -> canonical.exhaustive
                                                     -> Neo4j projection -> canonical.graph
```

Deferred: merge, split, supersession, temporal identity, successor graphs, cross-workspace identity,
advanced review/alias workflows, historical audit UI, full lifecycle API, conflict governance,
generic event/claims framework, current-world ownership truth, and general graph traversal.

## OWNER DECISION REQUIRED

1. **Multi-part surname policy:** withhold until exact extractor/manual evidence supports a governed
   parser (**recommended**), or introduce a tested Turkish parser now. The former avoids false filters.
2. **UUIDv7 source:** use a pinned dependency/approved local helper (**recommended**), or use UUIDv4
   initially. Both preserve opacity/stability; UUIDv7 improves local ordering.
