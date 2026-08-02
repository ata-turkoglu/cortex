# GraphRAG Boundary

Microsoft GraphRAG is canonical and exposed through a dedicated adapter with explicit
schemas and integration tests. NetworkX is secondary. Each workspace owns an isolated
GraphRAG root, while Qdrant resource types remain separate and every operation uses the
workspace filter.
