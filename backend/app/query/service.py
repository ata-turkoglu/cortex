"""Detached V2-only production query orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from ..core.config import get_settings
from .answer import AnswerDraft, AnswerEngine
from .answer_synthesis import AnswerSynthesizer, SynthesisOutcome, apply_synthesis, is_eligible
from .briefing import WorkspaceBriefing
from .context import ConversationContext
from .execution import GenerationScopeResolver, V2PlanExecutor
from .ir import IRVocabulary
from .orchestration import CompletenessReport, ReasoningPackage, reconcile_engine_results
from .planning import PlanningReadinessSnapshot
from .runtime import PreparedQuery, QueryV2PreparationService
from .runtime_inputs import V2RuntimeInputs
from .scope import GenerationScope
from .source_runtime import V2QueryEmbedder


@dataclass(frozen=True)
class V2ServiceTrace:
    workspace_id: str
    generation_id: str
    embedding_config_hash: str
    dense_result_count: int
    sparse_result_count: int
    fused_result_count: int
    validated_result_count: int
    reasoning_package_generation: str | None
    answer_status: str
    citation_count: int
    retrieval_query: str | None = None


@dataclass(frozen=True)
class V2QueryServiceResult:
    answer: AnswerDraft
    package: ReasoningPackage
    prepared: PreparedQuery
    trace: V2ServiceTrace
    synthesis: SynthesisOutcome | None = None


class _FixedScopeResolver:
    def __init__(self, scope: GenerationScope) -> None:
        self.scope = scope

    def resolve(self, workspace_id: str) -> GenerationScope:
        if workspace_id != self.scope.workspace_id:
            raise ValueError("GENERATION_SCOPE_WORKSPACE_MISMATCH")
        return self.scope


class V2QueryService:
    """Coordinate V2 preparation, generation-bound retrieval, and finalization.

    The caller owns short transactions for context/readiness loading and later
    persistence. This service never falls back to V1 or re-resolves scope.
    """

    def __init__(
        self,
        preparation: QueryV2PreparationService,
        scope_resolver: GenerationScopeResolver,
        query_embedder: V2QueryEmbedder,
        executor: V2PlanExecutor,
        *,
        data_root: Path,
        answer_engine: AnswerEngine | None = None,
        briefing_loader: Callable[[GenerationScope], WorkspaceBriefing] | None = None,
        property_vocabulary_loader: (
            Callable[[GenerationScope], dict[str, frozenset[str]]] | None
        ) = None,
        completeness_evaluator: Callable[[GenerationScope, object, int | None], object]
        | None = None,
        answer_synthesizer: AnswerSynthesizer | None = None,
    ) -> None:
        self.preparation = preparation
        self.scope_resolver = scope_resolver
        self.query_embedder = query_embedder
        self.executor = executor
        self.data_root = data_root
        self.answer_engine = answer_engine or AnswerEngine()
        self.briefing_loader = briefing_loader
        self.property_vocabulary_loader = property_vocabulary_loader
        self.completeness_evaluator = completeness_evaluator
        self.answer_synthesizer = answer_synthesizer

    async def execute(
        self,
        session: Session,
        query: str,
        context: ConversationContext,
        vocabulary: IRVocabulary,
        readiness: PlanningReadinessSnapshot,
        briefing: WorkspaceBriefing | None = None,
    ) -> V2QueryServiceResult:
        scope = self.scope_resolver.resolve(context.workspace_id)
        if briefing is None and self.briefing_loader is not None:
            briefing = self.briefing_loader(scope)
        if self.property_vocabulary_loader is not None:
            vocabulary = vocabulary.with_governed_properties(self.property_vocabulary_loader(scope))
        # No provider call may run while a database transaction is open.
        _end_read_transaction(session)
        prepared = await self.preparation.prepare(query, context, vocabulary, readiness, briefing)
        if scope.workspace_id != prepared.physical_plan.workspace_id:
            raise ValueError("GENERATION_SCOPE_WORKSPACE_MISMATCH")
        if prepared.physical_plan.state != "ready":
            return self._unsupported_result(prepared, scope)
        from ..knowledge.source_manifest import load_generation_manifest

        sources = load_generation_manifest(
            session, scope.workspace_id, scope.generation_id, self.data_root
        )
        _end_read_transaction(session)
        retrieval_query = _retrieval_query(query, prepared.semantic.understanding)
        vector = await self.query_embedder.embed(retrieval_query, scope)
        execution = self._execute_bound(prepared, scope, vector, retrieval_query, sources)
        contract = _reconciliation_contract(prepared.physical_plan, scope, prepared.logical_ir)
        result_steps = _final_result_steps(prepared.physical_plan, prepared.logical_ir)
        package = reconcile_engine_results(
            contract,
            tuple(result for result in execution.results if result.step_id in result_steps),
            sources,
        )
        package = self._apply_query_completeness(package, scope, prepared)
        package = _with_failure_reason(package)
        answer = self.answer_engine.render(package, query=query)
        synthesis = None
        if self.answer_synthesizer is not None and is_eligible(package):
            _end_read_transaction(session)
            synthesis = await self.answer_synthesizer.synthesize(query, package)
            answer = apply_synthesis(answer, package, synthesis)
        return V2QueryServiceResult(
            synthesis=synthesis,
            answer=answer,
            package=package,
            prepared=prepared,
            trace=V2ServiceTrace(
                workspace_id=scope.workspace_id,
                generation_id=scope.generation_id,
                embedding_config_hash=scope.embedding_config_hash,
                dense_result_count=sum(
                    result.trace.counters.get("dense_result_count", 0)
                    for result in execution.results
                ),
                sparse_result_count=sum(
                    result.trace.counters.get("sparse_result_count", 0)
                    for result in execution.results
                ),
                fused_result_count=sum(
                    result.trace.counters.get("fused_result_count", 0)
                    for result in execution.results
                ),
                validated_result_count=sum(
                    len(result.text_evidence) for result in execution.results
                ),
                reasoning_package_generation=package.generation_id,
                answer_status=answer.state,
                citation_count=len(answer.citations),
                retrieval_query=retrieval_query,
            ),
        )

    def _unsupported_result(
        self, prepared: PreparedQuery, scope: GenerationScope
    ) -> V2QueryServiceResult:
        """Use the normal Result & Evidence/Answer boundary for unavailable capabilities."""
        package = ReasoningPackage(
            workspace_id=scope.workspace_id,
            generation_id=scope.generation_id,
            state="unsupported",
            completeness=CompletenessReport(coverage="grounded", state="unknown"),
            confidence=0.0,
            issues=tuple(
                f"capability_unavailable:{issue}" for issue in prepared.physical_plan.issues
            ),
            failure_reason=_failure_reason(prepared),
        )
        answer = self.answer_engine.render(package)
        return V2QueryServiceResult(
            answer=answer,
            package=package,
            prepared=prepared,
            trace=V2ServiceTrace(
                workspace_id=scope.workspace_id,
                generation_id=scope.generation_id,
                embedding_config_hash=scope.embedding_config_hash,
                dense_result_count=0,
                sparse_result_count=0,
                fused_result_count=0,
                validated_result_count=0,
                reasoning_package_generation=package.generation_id,
                answer_status=answer.state,
                citation_count=0,
            ),
        )

    async def execute_inputs(
        self, session: Session, query: str, inputs: V2RuntimeInputs
    ) -> V2QueryServiceResult:
        """Execute one short-transaction runtime snapshot without a live re-resolution."""
        if inputs.generation_scope_resolver.scope != inputs.generation_scope:
            raise ValueError("runtime inputs contain inconsistent generation scope")
        bound = V2QueryService(
            self.preparation,
            inputs.generation_scope_resolver,
            self.query_embedder,
            self.executor,
            data_root=self.data_root,
            answer_engine=self.answer_engine,
            briefing_loader=self.briefing_loader,
            property_vocabulary_loader=self.property_vocabulary_loader,
            completeness_evaluator=self.completeness_evaluator,
            answer_synthesizer=self.answer_synthesizer,
        )
        return await bound.execute(
            session,
            query,
            inputs.conversation_context,
            inputs.vocabulary,
            inputs.readiness,
            inputs.workspace_briefing,
        )

    def _apply_query_completeness(self, package, scope, prepared: PreparedQuery):
        # Canonical population blockers describe structured results only; a grounded
        # retrieval answer has no population and must not inherit unrelated blockers
        # or report its top-k hit count as a known count.
        if self.completeness_evaluator is None or not _has_structured_result(
            prepared.physical_plan, prepared.logical_ir
        ):
            return package
        query = self.completeness_evaluator(scope, prepared.logical_ir, _known_count(package))
        completeness = package.completeness.model_copy(update={"query": query})
        if query.status == "COMPLETE":
            return package.model_copy(update={"completeness": completeness})
        if query.status == "UNAVAILABLE":
            return package.model_copy(
                update={
                    "state": "unsupported",
                    "completeness": completeness,
                    "issues": package.issues + tuple(query.reasons),
                }
            )
        return package.model_copy(update={"state": "partial", "completeness": completeness})

    def _execute_bound(
        self, prepared: PreparedQuery, scope: GenerationScope, vector, query: str, sources
    ):
        # A fixed resolver makes the one scope resolution an immutable request snapshot.
        return V2PlanExecutor(
            _FixedScopeResolver(scope),
            self.executor.dense,
            self.executor.sparse,
            self.executor.registry,
        ).execute_plan(
            prepared.physical_plan,
            prepared.logical_ir.nodes,
            query_vector=vector,
            query_text=query,
            trusted_sources=sources,
            dense_limit=get_settings().dense_top_k,
            sparse_limit=get_settings().bm25_top_k,
            fusion_limit=get_settings().fusion_candidate_limit,
        )


def _reconciliation_contract(plan, scope: GenerationScope, logical_ir):
    from .orchestration import ExpectedResultStep, ReconciliationContract

    steps = tuple(
        ExpectedResultStep(step_id=step.step_id, engine=step.engine, capability=step.capability)
        for step in plan.graph.steps
        if step.step_id in _final_result_steps(plan, logical_ir)
    )
    exhaustive = any(step.coverage_expectation == "exhaustive" for step in plan.graph.steps)
    return ReconciliationContract(
        workspace_id=scope.workspace_id,
        generation_id=scope.generation_id,
        coverage=("exhaustive" if exhaustive else "grounded"),
        boundary=(logical_ir.coverage.population_boundary if exhaustive else None),
        expected_steps=steps,
    )


def _has_structured_result(plan, logical_ir) -> bool:
    if plan.graph is None:
        return False
    by_id = {step.step_id: step for step in plan.graph.steps}
    return any(
        by_id[step_id].engine == "structured" for step_id in _final_result_steps(plan, logical_ir)
    )


def _end_read_transaction(session: Session) -> None:
    """Close a read-only transaction before awaiting a provider or network call."""
    if session.in_transaction() and not (session.new or session.dirty or session.deleted):
        session.commit()


def _retrieval_query(query: str, understanding) -> str:
    """Make conversation-resolved referents visible to dense and sparse retrieval.

    A follow-up such as "onun mülkleri?" carries its referent only in the semantic
    understanding; the raw text alone would retrieve evidence for a pronoun.
    """
    names = [
        entity.display_name
        for entity in understanding.entities
        if entity.reference_kind != "explicit"
        and entity.resolution == "resolved"
        and entity.display_name
        and entity.display_name.casefold() not in query.casefold()
    ]
    return " ".join((query, *dict.fromkeys(names)))


def _known_count(package) -> int | None:
    """Return only a directly represented canonical count; never estimate one."""
    if package.aggregates:
        value = package.aggregates[0].value
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    if package.structured_rows:
        return len(package.structured_rows)
    return 0 if package.completeness.confirmed_count == 0 else None


def _failure_reason(prepared: PreparedQuery) -> str:
    """Classify known safe-stop causes without exposing planner/provider prose."""
    understanding = prepared.semantic.understanding
    entity_states = {entity.resolution for entity in understanding.entities}
    if "ambiguous" in entity_states or understanding.state == "ambiguous":
        return "identity_ambiguous"
    if "unresolved" in entity_states and (
        understanding.structured_operation is not None
        or understanding.relations
        or understanding.typed_filters
    ):
        return "identity_unresolved"
    if prepared.physical_plan.state == "unresolved":
        return "query_not_understood"
    return "unsupported_operation"


def _with_failure_reason(package: ReasoningPackage) -> ReasoningPackage:
    """Make every fail-closed result carry a typed renderer reason."""
    if package.state != "unsupported" or package.failure_reason is not None:
        return package
    return package.model_copy(update={"failure_reason": "insufficient_evidence"})


def _final_result_steps(plan, logical_ir) -> frozenset[str]:
    """Return only material results that implement a final logical root.

    A root such as ``SummarizeNode`` is executed by the non-material reasoning
    boundary. Its nearest material dependency is the result to reconcile; scan
    prerequisites farther upstream must not leak into the user-facing result.
    """
    if plan.graph is None:
        return frozenset()
    by_id = {step.step_id: step for step in plan.graph.steps}
    root_ids = set(logical_ir.root_ids)
    selected: set[str] = set()

    def collect(step_id: str) -> None:
        step = by_id[step_id]
        if step.engine not in {"result_evidence", "reasoning"}:
            selected.add(step_id)
            return
        for dependency in step.dependencies:
            collect(dependency)

    for step in plan.graph.steps:
        if set(step.trace.logical_node_ids) & root_ids:
            collect(step.step_id)
    return frozenset(selected)
