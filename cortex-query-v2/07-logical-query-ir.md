# Phase 07 — Logical Query IR

## Goal

Build a typed, versioned Logical Query IR that represents user meaning independently of execution.

## Model

Use a composable DAG/expression graph, not a closed question taxonomy. Operator families include Scan, Resolve, Filter, Traverse, Join, Distinct, Group, Aggregate, Count, Rank, Sort, Limit, Project, TemporalConstraint, RetrieveEvidence, Compare, Exists, Summarize, and CustomCapability.

## Requirements and acceptance

Support targets, constraints, relations, temporal semantics, aggregation/grouping, coverage, output projection, evidence requirements, ambiguity/candidate plans, extension nodes, and versioning. Validate schemas/types/semantics, invalid relations/fields, incompatible coverage, and safe repair. Represent count/list/all/group/rank/min/max/top-N/population comparison without adding intent enums for new language forms.

## Delivery status

- [x] Versioned `LogicalQueryIR` with a typed composable DAG and all nineteen required operator
  families, including governed extension nodes.
- [x] Explicit workspace scope, targets/resources, fields, relations, temporal predicates, coverage,
  output projection, evidence requirements, ambiguity candidates, and unresolved issues.
- [x] Fail-closed schema, DAG, input/output type, upstream projection, vocabulary, workspace,
  coverage, and evidence validation.
- [x] Exhaustive representations for list/count/group/min/max/rank/top-N/population comparison that
  reject discovery/top-k coverage and weak provenance contracts.
- [x] Deterministic semantic-understanding lowering plus meaning-preserving safe repair limited to
  duplicate graph references and a missing schema-version marker.
- [x] Focused operator, invalid graph/type/vocabulary/scope/coverage, ambiguity, temporal, lowering,
  safe-repair, and Phase 06 regression tests; architecture and AI-context documentation updated.

Phase 07 remains disconnected from V1 chat. Execution Planning is Phase 08; no physical route or
engine is selected here. Phase 05A remains deferred and this phase makes no indexing-cutover or
corpus-completeness claim.
