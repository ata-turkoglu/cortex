# GraphRAG Context

Read the root and backend instructions first. Keep Microsoft GraphRAG behind a dedicated
adapter boundary. GraphRAG data is workspace-isolated; Local, Global, and DRIFT paths
remain independently testable and never bypass the workspace context.
