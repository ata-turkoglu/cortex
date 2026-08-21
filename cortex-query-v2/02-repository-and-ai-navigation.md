# Phase 02 — Repository Boundaries & AI Navigation

## Goal

Establish real subsystem boundaries before V2 implementation.

## Target shape

```text
backend/app/query/{context,understanding,ir,planning,orchestration}/
backend/app/knowledge/{entities,relations,events,temporal,claims,provenance}/
backend/app/engines/{structured,graph,retrieval,graphrag,hybrid}/
backend/app/reasoning/{research,composition}/
```

Adapt names to repository conventions when needed; do not create duplicate runtimes.

## AI navigation

Relevant parent and child folders contain `AGENTS.md` and `CLAUDE.md`.

- Parents route to children; children link back to parent invariants.
- Update `.ai/project-map.yaml` and `docs/ai/index.md`.
- Evaluate scoped context for every change.
- Root → parent → child navigation works.

## Acceptance

Behavior remains V1-equivalent; this is a repository-boundary refactor only.
