"""Short-transaction workflow steps for research decomposition and collection."""

from ...query.orchestration.schemas import ReasoningPackage
from .schemas import CrossSourceClaim, ResearchCheckpoint, ResearchPlanner, ResearchSubquery
from .store import load_research_run, save_research_run


def execute_decomposition(
    run_id: str, workspace_id: str, session_factory, planner: ResearchPlanner
):
    session = session_factory()
    try:
        checkpoint, revision = load_research_run(session, workspace_id, run_id)
        if checkpoint.decomposition is not None:
            return checkpoint
        running = checkpoint.model_copy(update={"state": "decomposing"})
        revision = save_research_run(session, running, expected_revision=revision)
        session.commit()
        goal = running.goal
    finally:
        session.close()
    # The provider/planner receives detached primitives and no SQLAlchemy session.
    decomposition = planner.decompose(goal, workspace_id)
    planned = running.model_copy(update={"state": "planned", "decomposition": decomposition})
    session = session_factory()
    try:
        save_research_run(session, planned, expected_revision=revision)
        session.commit()
    finally:
        session.close()
    return planned


def update_subquery(
    checkpoint: ResearchCheckpoint, updated: ResearchSubquery
) -> ResearchCheckpoint:
    if checkpoint.decomposition is None:
        raise ValueError("research has not been decomposed")
    found = False
    items = []
    for item in checkpoint.decomposition.subqueries:
        if item.subquery_id == updated.subquery_id:
            items.append(updated)
            found = True
        else:
            items.append(item)
    if not found:
        raise ValueError("research subquery is not declared")
    decomposition = checkpoint.decomposition.model_copy(update={"subqueries": tuple(items)})
    return checkpoint.model_copy(update={"decomposition": decomposition, "state": "executing"})


def collect_evidence(
    checkpoint: ResearchCheckpoint, subquery_id: str, package: ReasoningPackage
) -> ResearchCheckpoint:
    if package.workspace_id != checkpoint.workspace_id:
        raise ValueError("research evidence cannot cross the run workspace")
    if checkpoint.generation_id and package.generation_id != checkpoint.generation_id:
        raise ValueError("research evidence cannot mix generations")
    if package.state in {"unsupported", "ambiguous"}:
        state, issue = "failed", f"evidence package is {package.state}"
    else:
        state, issue = "collected", None
    if checkpoint.decomposition is None:
        raise ValueError("research has not been decomposed")
    current = next(
        (item for item in checkpoint.decomposition.subqueries if item.subquery_id == subquery_id),
        None,
    )
    if current is None:
        raise ValueError("research subquery is not declared")
    return update_subquery(
        checkpoint,
        current.model_copy(update={"state": state, "package": package, "issue": issue}),
    )


def finalize_research(
    checkpoint: ResearchCheckpoint, claims: tuple[CrossSourceClaim, ...]
) -> ResearchCheckpoint:
    if checkpoint.decomposition is None:
        raise ValueError("research has not been decomposed")
    subqueries = checkpoint.decomposition.subqueries
    collected = [item for item in subqueries if item.state == "collected"]
    if not collected:
        return checkpoint.model_copy(update={
            "state": "unsupported", "validation_state": "failed",
            "issues": ("no research subquery produced trustworthy evidence",),
        })
    complete = len(collected) == len(subqueries)
    state = "ready" if complete else "partial"
    validation = "grounded" if complete else "partial"
    candidate = checkpoint.model_copy(update={
        "state": state, "claims": claims, "validation_state": validation,
        "issues": () if complete else ("one or more research subqueries failed",),
    })
    return ResearchCheckpoint.model_validate(candidate.model_dump())
