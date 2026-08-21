# Query V2 Context

Read the root and `backend/AGENTS.md`, then the canonical Query V2 architecture and invariants.
Choose the smallest child boundary: `context/`, `understanding/`, `ir/`, `planning/`, or
`orchestration/`. Query meaning must remain separate from physical engine selection, and no
execution engine may author or persist the final answer.

The active V1 implementation remains in `app/chat/` until its owning V2 phase migrates it. Do not
copy V1 implementations into this tree or present its `intent`/route contracts as V2 contracts.
