# Phase 1 — Repository and AI Context

## Goal

Create the monorepo structure, development conventions, vendor-neutral AI context system, and base documentation.

## Checklist

- [x] Create root project structure for `frontend`, `backend`, `infrastructure`, `docs`, `scripts`, and `data`.
- [x] Create root `AGENTS.md` as the canonical AI instruction entry point.
- [x] Create thin `CLAUDE.md` and `GEMINI.md` adapters.
- [x] Create scoped `AGENTS.md` files for frontend, backend, retrieval, GraphRAG, workflows, and infrastructure.
- [x] Create `.ai/project-map.yaml`.
- [x] Create `docs/ai/index.md` and concise module maps.
- [x] Create `docs/architecture`, `docs/workflows`, `docs/api`, and `docs/frontend`.
- [x] Create `scripts/ai-context/generate-adapters.py`.
- [x] Create `scripts/ai-context/validate-context.py`.
- [x] Create `scripts/ai-context/check-context-freshness.py`.
- [x] Add generated/data/model/cache/log/dependency exclusions to documentation and ignore files.
- [x] Add a rule requiring architecture/context documentation updates for public-contract changes.
- [x] Add formatting, linting, and pre-commit configuration.
- [x] Validate all documented paths.
- [x] Update `IMPLEMENTATION_STATUS.md`.

## Acceptance criteria

- [x] AI tools can identify the relevant module without scanning the whole repository.
- [x] Adapter files contain no duplicated architecture content.
- [x] Validation scripts pass.
- [x] Ignore rules cover generated and large runtime directories.

## Additional checklist

- [x] Create exact-version dependency policy documentation.
- [x] Add `THIRD_PARTY_NOTICES.md`.
- [x] Add automated license-check configuration where practical.
- [x] Add architecture documentation for API contracts, SQLite concurrency, file security, crash recovery, and orphan reconciliation.
- [x] Add V1 page inventory documentation.
