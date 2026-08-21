# Canonical Graph Storage

Read parent `../AGENTS.md`, the knowledge-construction contract, and the scoped GraphRAG context.
Own the Cortex graph adapter and Neo4j persistence contracts. Direct Neo4j driver imports must stay
inside this boundary. Every operation is bound to one workspace, and extracted/canonical layers
remain logically separate in the same database. Never let a GraphRAG extraction overwrite
canonical or user-curated knowledge.
