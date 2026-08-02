# Phase 4 — Database and Workspace

## Goal

Implement the V1 relational data model, workspace isolation, resource mappings, and WorkspaceContext.

## Checklist

- [x] Create `workspaces`.
- [x] Create `workspace_resources`.
- [x] Create folders and document tables.
- [x] Create `documents`.
- [x] Create `document_versions`.
- [x] Create chunks and chunk relationships.
- [x] Create conversations and messages.
- [x] Create message citations/evidence references.
- [x] Create workflow definitions/runs/step runs/events.
- [x] Create query runs/query step runs.
- [x] Create jobs or normalize jobs through workflow runs.
- [x] Create settings tables.
- [x] Create provider/model/layer-assignment tables.
- [x] Create workspace index state.
- [x] Create GraphRAG state and pending-document tracking.
- [x] Create soft-delete fields and indexes.
- [x] Create content-hash and deduplication fields.
- [x] Implement `WorkspaceContext`.
- [x] Make `WorkspaceContext` resolve paths, resource names, graph roots, cache paths, and state.
- [x] Create workspace CRUD API.
- [x] Create workspace deletion safety behavior.
- [x] Add database constraints and indexes.
- [x] Add migrations.
- [x] Add workspace isolation tests.
- [x] Update `IMPLEMENTATION_STATUS.md`.

## Acceptance criteria

- [x] Every workspace-scoped table has `workspace_id`.
- [x] Resource names are resolved through WorkspaceContext.
- [x] Cross-workspace access tests fail safely.
- [x] Soft delete works.
- [x] Migrations apply from an empty database.

## Additional checklist

- [x] Add interrupted/recovery states to workflow/job schemas.
- [x] Add reconciliation/repair job types.
- [x] Add indexes required for server-side pagination.
- [x] Add database tests for WAL, foreign keys, busy timeout, and lock retry behavior.
- [x] Add migration tests that preserve existing data.

## Additional checklist — cost and setup persistence

- [x] Persist setup-completion state.
- [x] Persist provider validation metadata without secrets.
- [x] Persist per-layer model defaults.
- [x] Persist token usage and estimated cost by query/workflow/workspace/layer/model.
- [x] Persist daily and monthly budget settings.
