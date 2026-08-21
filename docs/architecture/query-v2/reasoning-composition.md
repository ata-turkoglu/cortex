# Query V2 reasoning, research, and composition

Phase 11 implements the inactive V2 reasoning boundary without changing V1 chat. A normal query
may pass one reconciled `ReasoningPackage` directly toward the later Answer Engine; a larger goal
uses durable research and composition runs instead of being forced into one Logical Query IR.

`ResearchCheckpoint` owns the research goal, generation, dependency-ordered subqueries, optional
Logical Query IR and physical plan for each subquery, reconciled evidence packages, cross-source
claims, issues, and validation state. Every IR, plan, and package must match the run workspace;
generation-bound research cannot mix package generations. A claim must cite evidence collected by
its declared subqueries. Ambiguous or unsupported packages remain visible and prevent a falsely
complete research result.

`CompositionCheckpoint` owns a contiguous outline, independently resumable sections, paragraphs,
sentences, consistency issues, and the final artifact. Every factual sentence has one or more
collected evidence IDs. Final assembly is allowed only when every outline section is validated and
the artifact's sentence-evidence map exactly equals the internal draft lineage. This preserves
grounding through long-form output rather than attaching citations only after prose is written.

`research_runs` and `composition_runs` persist versioned JSON checkpoints with optimistic
revisions and workspace ownership. External planners/composers operate on detached primitives
between short transactions. A stopped run resumes from completed decomposition, evidence, or
section checkpoints. Phase 11 does not persist an assistant answer and remains disconnected from
V1 chat; the later Answer Engine and Phase 13 cutover own user-facing activation.
