"""Built-in physical capability declarations; readiness remains runtime supplied."""

from __future__ import annotations

from .schemas import CapabilityDeclaration

SET_TYPES = (
    "entity_set",
    "record_set",
    "document_set",
    "event_set",
    "grouped_set",
    "ranked_set",
    "graph_paths",
)


def _cap(
    engine: str,
    capability: str,
    outputs: tuple[str, ...],
    *,
    inputs: tuple[str, ...] = (),
    coverage: str = "grounded",
    generation: bool = True,
    projections: tuple[str, ...] = (),
    quality: tuple[int, int, int, int, int, int] = (100, 90, 90, 80, 50, 50),
) -> CapabilityDeclaration:
    correctness, evidence, coverage_quality, reasoning, latency, cost = quality
    return CapabilityDeclaration(
        engine=engine,
        capability=capability,
        input_types=inputs,
        output_types=outputs,
        maximum_coverage=coverage,
        requires_generation=generation,
        required_projections=projections,
        correctness=correctness,
        evidence_quality=evidence,
        coverage_quality=coverage_quality,
        reasoning_quality=reasoning,
        latency=latency,
        cost=cost,
    )


DEFAULT_CAPABILITIES: tuple[CapabilityDeclaration, ...] = (
    _cap("structured", "structured.enumerate", SET_TYPES[:-1], coverage="exhaustive"),
    *(
        _cap("structured", f"structured.{name}", outputs, inputs=SET_TYPES, coverage="exhaustive")
        for name, outputs in (
            ("filter", SET_TYPES),
            ("join", ("record_set",)),
            ("distinct", SET_TYPES),
            ("group", ("grouped_set",)),
            ("aggregate", ("scalar", "record_set")),
            ("count", ("scalar", "record_set")),
            ("rank", ("ranked_set",)),
            ("sort", SET_TYPES),
            ("limit", SET_TYPES),
            ("project", ("record_set",)),
            ("temporal_filter", SET_TYPES),
            ("compare", ("comparison_result",)),
            ("exists", ("boolean",)),
        )
    ),
    _cap("knowledge_graph", "graph.entity_resolve", ("entity_set",)),
    _cap(
        "knowledge_graph",
        "graph.traverse",
        ("entity_set", "graph_paths"),
        inputs=("entity_set",),
    ),
    _cap(
        "knowledge_graph",
        "graph.multi_hop",
        ("entity_set", "graph_paths"),
        inputs=("entity_set",),
    ),
    _cap("knowledge_graph", "graph.temporal_reasoning", SET_TYPES, inputs=SET_TYPES),
    _cap("knowledge_graph", "graph.event_participation", ("extension",), inputs=SET_TYPES),
    _cap("knowledge_graph", "graph.provenance_traversal", ("extension",), inputs=SET_TYPES),
    _cap("knowledge_graph", "graph.contradiction_analysis", ("extension",), inputs=SET_TYPES),
    _cap("retrieval", "retrieval.hybrid_search", ("evidence_set",), inputs=SET_TYPES),
    _cap(
        "retrieval",
        "retrieval.semantic_search",
        ("evidence_set",),
        inputs=SET_TYPES,
        quality=(95, 85, 75, 80, 35, 35),
    ),
    *(
        _cap("graphrag", f"graphrag.{mode}", ("extension",), inputs=SET_TYPES)
        for mode in ("local", "global", "drift", "community_context")
    ),
    _cap(
        "reasoning",
        "reasoning.evidence_synthesis",
        ("summary_request",),
        inputs=("evidence_set", "extension", "comparison_result", "record_set", "graph_paths"),
        generation=False,
    ),
    _cap(
        "reasoning",
        "reasoning.long_form_research",
        ("extension",),
        inputs=SET_TYPES + ("evidence_set", "extension"),
        generation=False,
    ),
    _cap(
        "result_evidence",
        "evidence.reconcile_and_validate",
        ("evidence_package",),
        generation=False,
        coverage="exhaustive",
    ),
)
