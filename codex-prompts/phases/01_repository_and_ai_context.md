# Phase 1 — Repository and AI Context

## Goal

Create the monorepo structure, development conventions, vendor-neutral AI context system, and base documentation.

## Checklist

- [ ] Create root project structure for `frontend`, `backend`, `infrastructure`, `docs`, `scripts`, and `data`.
- [ ] Create root `AGENTS.md` as the canonical AI instruction entry point.
- [ ] Create thin `CLAUDE.md` and `GEMINI.md` adapters.
- [ ] Create scoped `AGENTS.md` files for frontend, backend, retrieval, GraphRAG, workflows, and infrastructure.
- [ ] Create `.ai/project-map.yaml`.
- [ ] Create `docs/ai/index.md` and concise module maps.
- [ ] Create `docs/architecture`, `docs/workflows`, `docs/api`, and `docs/frontend`.
- [ ] Create `scripts/ai-context/generate-adapters.py`.
- [ ] Create `scripts/ai-context/validate-context.py`.
- [ ] Create `scripts/ai-context/check-context-freshness.py`.
- [ ] Add generated/data/model/cache/log/dependency exclusions to documentation and ignore files.
- [ ] Add a rule requiring architecture/context documentation updates for public-contract changes.
- [ ] Add formatting, linting, and pre-commit configuration.
- [ ] Validate all documented paths.
- [ ] Update `IMPLEMENTATION_STATUS.md`.

## Acceptance criteria

- [ ] AI tools can identify the relevant module without scanning the whole repository.
- [ ] Adapter files contain no duplicated architecture content.
- [ ] Validation scripts pass.
- [ ] Ignore rules cover generated and large runtime directories.

## Additional checklist

- [ ] Create exact-version dependency policy documentation.
- [ ] Add `THIRD_PARTY_NOTICES.md`.
- [ ] Add automated license-check configuration where practical.
- [ ] Add architecture documentation for API contracts, SQLite concurrency, file security, crash recovery, and orphan reconciliation.
- [ ] Add V1 page inventory documentation.
