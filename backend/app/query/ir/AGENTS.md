# Logical Query IR

Read parent `../AGENTS.md` and the Query V2 runtime contract. Own the versioned typed logical DAG,
operator schemas, validation, ambiguity, coverage, and evidence requirements. IR is independent of
providers, persistence implementations, and physical engines; do not grow a closed intent taxonomy.
Use discriminated nodes from `schemas.py`, validate workspace vocabulary and semantic invariants
through `validation.py`, and lower only sufficiently typed semantic meaning through `lowering.py`.
Safe repair may remove representation noise but must never invent fields, relations, or semantics.
