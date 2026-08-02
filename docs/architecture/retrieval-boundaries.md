# Retrieval Boundary

LlamaIndex routes Hybrid Search and separate GraphRAG Local, Global, and DRIFT engines.
Hybrid search combines workspace-filtered Qdrant dense retrieval, bm25s sparse retrieval,
fusion, and a local BGE reranker. Embedding configuration changes require dense reindexing;
vectors with incompatible dimensions/configurations may never share an active vector field.
