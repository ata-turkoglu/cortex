# Query V2 production evaluation

`backend/app/evaluation` has two intentionally separate evaluation paths.

## Production acceptance gate

Run the active production gate from `backend`:

```powershell
.\.venv\Scripts\python.exe -m app.evaluation
```

This executes the versioned `uploaded-file-production-v2/v1` acceptance in an isolated process. Its
single atomic contract scenario provisions a disposable SQLite database, local Qdrant, artifact
root, deterministic provider adapters, and FastAPI dependency overrides. It then verifies:

- upload through immutable source-manifest and exact-generation construction;
- generation-owned BM25 and generation-filtered Qdrant retrieval with dense+sparse fusion;
- grounded citations whose identity and content hash resolve to the trusted manifest;
- grounded and unsupported normal `POST /chat` persistence;
- workspace/generation isolation and no V1 chat, hybrid runtime, workspace-only dense, or legacy
  BM25 reachability;
- post-activation manifest tampering fails closed as a persisted V2 unsupported response with zero
  citations and no fallback.

The report includes a `CutoverEvaluation`-compatible payload. The mandatory case scores `1.0` only
when the whole scenario passes; a failed subprocess produces score `0.0` and the mandatory failure
identifier. It is therefore safe to supply as a detached cutover input and cannot turn a failed
acceptance into an activation-ready result.

## Historical V1 benchmark

The former synthetic V1 golden runner (`--historical-v1`) was removed together with the V1 chat
orchestration it exercised. `python -m app.evaluation` runs only the V2 production acceptance
contract above.

Private verified document packs may be added under `backend/evaluation/local/` using the versioned
schema when source documents and human labels are supplied. They complement—but do not replace—the
mandatory deterministic production contract above.