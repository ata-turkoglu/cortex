# Phase 4 — Database and Workspace

## Goal

Implement the V1 relational data model, workspace isolation, resource mappings, and WorkspaceContext.

## Checklist

- [ ] Create `workspaces`.
- [ ] Create `workspace_resources`.
- [ ] Create folders and document tables.
- [ ] Create `documents`.
- [ ] Create `document_versions`.
- [ ] Create chunks and chunk relationships.
- [ ] Create conversations and messages.
- [ ] Create message citations/evidence references.
- [ ] Create workflow definitions/runs/step runs/events.
- [ ] Create query runs/query step runs.
- [ ] Create jobs or normalize jobs through workflow runs.
- [ ] Create settings tables.
- [ ] Create provider/model/layer-assignment tables.
- [ ] Create workspace index state.
- [ ] Create GraphRAG state and pending-document tracking.
- [ ] Create soft-delete fields and indexes.
- [ ] Create content-hash and deduplication fields.
- [ ] Implement `WorkspaceContext`.
- [ ] Make `WorkspaceContext` resolve paths, resource names, graph roots, cache paths, and state.
- [ ] Create workspace CRUD API.
- [ ] Create workspace deletion safety behavior.
- [ ] Add database constraints and indexes.
- [ ] Add migrations.
- [ ] Add workspace isolation tests.
- [ ] Update `IMPLEMENTATION_STATUS.md`.

## Acceptance criteria

- [ ] Every workspace-scoped table has `workspace_id`.
- [ ] Resource names are resolved through WorkspaceContext.
- [ ] Cross-workspace access tests fail safely.
- [ ] Soft delete works.
- [ ] Migrations apply from an empty database.

## Additional checklist

- [ ] Add interrupted/recovery states to workflow/job schemas.
- [ ] Add reconciliation/repair job types.
- [ ] Add indexes required for server-side pagination.
- [ ] Add database tests for WAL, foreign keys, busy timeout, and lock retry behavior.
- [ ] Add migration tests that preserve existing data.

## Additional checklist — cost and setup persistence

- [ ] Persist setup-completion state.
- [ ] Persist provider validation metadata without secrets.
- [ ] Persist per-layer model defaults.
- [ ] Persist token usage and estimated cost by query/workflow/workspace/layer/model.
- [ ] Persist daily and monthly budget settings.
