# Query V2 Context

Read the root and `backend/AGENTS.md`, then the canonical Query V2 architecture and invariants.
Choose the smallest child boundary: `context/`, `understanding/`, `ir/`, `planning/`, or
`orchestration/`. Query meaning must remain separate from physical engine selection, and no
execution engine may author or persist the final answer.

Production query execution is V2-only through `app/query/production_chat.py`. The V1 `app/chat/`
orchestration has been removed; do not recreate it in this tree.
