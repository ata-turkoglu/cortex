# Cortex High-Risk Implementation Boundaries

Codex must treat these as high-risk and test them independently.

## 1. GraphRAG–Qdrant adapter

Risks:

- upstream API drift
- mismatched schemas
- workspace leakage
- vector-dimension mismatch
- Local/Global/DRIFT behavior changes

Required mitigation:

- dedicated adapter
- explicit contracts
- integration tests
- compatibility notes

## 2. SQLite concurrency

Risks:

- backend/worker lock contention
- long transactions
- stale writes
- crash recovery

Required mitigation:

- WAL
- busy timeout
- short transactions
- bounded retry
- recovery tests

## 3. Durable workflows

Risks:

- jobs stuck in running state
- partial external writes
- unsafe retry
- broken cancellation

Required mitigation:

- idempotency
- checkpoints
- interrupted state
- startup recovery
- reconciliation jobs

## 4. OpenAPI-generated frontend client

Risks:

- backend/frontend contract drift
- duplicated DTOs
- stale generated client

Required mitigation:

- generation command
- CI drift check
- feature-code import rules

## 5. Upload security

Risks:

- path traversal
- spoofed file type
- oversized files
- corrupt/encrypted documents

Required mitigation:

- filename normalization
- extension + MIME checks
- size limits
- structured errors
- tests
