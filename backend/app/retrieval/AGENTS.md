# Retrieval Context

Read `AGENTS.md` at the repository root and `backend/AGENTS.md` first. Retrieval must
preserve workspace isolation: every Qdrant read, write, and delete requires a workspace
filter. Keep embedding and reranking adapter-specific behavior out of feature services.
