import pytest

from app.engines.structured.engine import _compare
from app.knowledge.entities import (
    CanonicalEntityProperty,
    EntityPropertyValueType,
    normalize_mention,
)
from app.knowledge.model import KnowledgeAuthority, new_canonical_id
from app.knowledge.provenance import ExactSourceProvenance
from app.query.ir import IRVocabulary, lower_semantic_understanding, validate_logical_ir
from app.query.ir.schemas import CompareNode, CountNode, FilterNode, GroupNode, RankNode, ScanNode
from app.query.ir.validation import IRValidationError
from app.query.planning import (
    CapabilityReadiness,
    PlanningReadinessSnapshot,
    plan_execution,
)
from app.query.understanding import (
    SemanticGovernedField,
    SemanticTypedFilter,
    SemanticUnderstanding,
)


def _provenance(generation="generation-a"):
    return ExactSourceProvenance(
        workspace_id="workspace-a", document_id="doc", document_version_id="version",
        logical_document_id="logical", chunk_id="chunk", start_offset=4, end_offset=10,
        source_text="Merter", extraction_run_id="run", provider="test", model="test",
        prompt_version="v1", schema_version="v1", confidence=1, validation_state="extracted",
        generation=generation,
    )


def test_governed_surname_is_normalized_and_provenanced():
    item = CanonicalEntityProperty(
        new_canonical_id(), new_canonical_id(), "surname", "MERTer",
        EntityPropertyValueType.STRING, KnowledgeAuthority.EXTRACTED, "generation-a", _provenance(),
    )
    assert item.normalized_value == normalize_mention("Merter")
    assert item.provenance.evidence_id


def test_vocabulary_rejects_invented_or_wrong_resource_property():
    vocabulary = IRVocabulary.core().with_governed_properties({"person": frozenset({"surname"})})
    assert "surname" in vocabulary.resources["person"]
    assert "surname" not in vocabulary.resources["organization"]


def test_typed_filter_lowers_only_through_governed_ir_field():
    semantic = SemanticUnderstanding(
        state="resolved", confidence=1, coverage="relevant_evidence",
        typed_filters=(
            SemanticTypedFilter(
                target_type="person", property="surname", operator="eq", value="Merter"
            ),
        ),
    )
    ir = lower_semantic_understanding(semantic, "workspace-a")
    assert any(isinstance(node, FilterNode) and node.field.field == "surname" for node in ir.nodes)
    validate_logical_ir(
        ir, IRVocabulary.core().with_governed_properties({"person": frozenset({"surname"})})
    )


def test_structured_list_and_count_lower_to_exhaustive_governed_plans():
    vocabulary = IRVocabulary.core().with_governed_properties({"person": frozenset({"surname"})})
    readiness = PlanningReadinessSnapshot(
        workspace_id="workspace-a",
        active_generation_id="generation-a",
        capabilities=(
            CapabilityReadiness(
                workspace_id="workspace-a", engine="structured", capability="structured.enumerate",
                state="ready", generation_id="generation-a", ready_projections=("canonical_graph",),
            ),
            CapabilityReadiness(
                workspace_id="workspace-a", engine="structured", capability="structured.filter",
                state="ready", generation_id="generation-a", ready_projections=("canonical_graph",),
            ),
            CapabilityReadiness(
                workspace_id="workspace-a", engine="structured", capability="structured.count",
                state="ready", generation_id="generation-a", ready_projections=("canonical_graph",),
            ),
            CapabilityReadiness(
                workspace_id="workspace-a", engine="result_evidence",
                capability="evidence.reconcile_and_validate", state="ready",
            ),
        ),
    )

    def semantic(operation):
        return SemanticUnderstanding(
            state="resolved", confidence=1, coverage="corpus_required",
            structured_operation=operation,
            typed_filters=(
                SemanticTypedFilter(
                    target_type="person", property="surname", operator="eq", value="Merter"
                ),
            ),
        )

    list_ir = lower_semantic_understanding(semantic("list"), "workspace-a")
    count_ir = lower_semantic_understanding(semantic("count"), "workspace-a")
    assert any(
        isinstance(node, ScanNode) and node.population_mode == "exhaustive"
        for node in list_ir.nodes
    )
    assert any(isinstance(node, CountNode) for node in count_ir.nodes)
    assert plan_execution(list_ir, vocabulary, readiness).state == "ready"
    assert plan_execution(count_ir, vocabulary, readiness).state == "ready"


def test_surname_filter_never_derives_from_display_name():
    # The structured filter reads the governed field only. A display label is never consulted.
    record = {"display_name": "Ali Merter"}
    assert _compare(record.get("surname"), "eq", "Merter", normalized_string=True) is False


def test_governed_group_rank_and_compare_lower_to_exhaustive_structured_roots():
    field = SemanticGovernedField(target_type="person", property="surname")
    group = lower_semantic_understanding(
        SemanticUnderstanding(
            state="resolved",
            structured_operation="group",
            group_by=field,
            coverage="corpus_required",
            confidence=1,
        ),
        "workspace-a",
    )
    rank = lower_semantic_understanding(
        SemanticUnderstanding(
            state="resolved",
            structured_operation="rank",
            group_by=field,
            rank_direction="descending",
            coverage="corpus_required",
            confidence=1,
        ),
        "workspace-a",
    )
    compare = lower_semantic_understanding(
        SemanticUnderstanding(
            state="resolved",
            structured_operation="compare",
            typed_filters=(
                SemanticTypedFilter(
                    target_type="person", property="surname", operator="eq", value="Merter"
                ),
                SemanticTypedFilter(
                    target_type="person", property="surname", operator="eq", value="Subasi"
                ),
            ),
            coverage="corpus_required",
            confidence=1,
        ),
        "workspace-a",
    )

    vocabulary = IRVocabulary.core().with_governed_properties({"person": frozenset({"surname"})})
    assert isinstance(group.nodes[-1], GroupNode)
    assert isinstance(rank.nodes[-1], RankNode)
    assert rank.nodes[-1].measure == "canonical_count"
    assert isinstance(compare.nodes[-1], CompareNode)
    assert validate_logical_ir(group, vocabulary) is group
    assert validate_logical_ir(rank, vocabulary) is rank
    assert validate_logical_ir(compare, vocabulary) is compare


def test_invalid_governed_group_and_compare_fields_fail_before_material_execution():
    vocabulary = IRVocabulary.core().with_governed_properties({"person": frozenset({"surname"})})
    invalid_group = lower_semantic_understanding(
        SemanticUnderstanding(
            state="resolved",
            structured_operation="group",
            group_by=SemanticGovernedField(target_type="person", property="favorite_color"),
            coverage="corpus_required",
            confidence=1,
        ),
        "workspace-a",
    )
    invalid_compare = lower_semantic_understanding(
        SemanticUnderstanding(
            state="resolved",
            structured_operation="compare",
            typed_filters=(
                SemanticTypedFilter(
                    target_type="organization", property="surname", operator="eq", value="A"
                ),
                SemanticTypedFilter(
                    target_type="organization", property="surname", operator="eq", value="B"
                ),
            ),
            coverage="corpus_required",
            confidence=1,
        ),
        "workspace-a",
    )

    with pytest.raises(IRValidationError, match="favorite_color"):
        validate_logical_ir(invalid_group, vocabulary)
    with pytest.raises(IRValidationError, match="surname"):
        validate_logical_ir(invalid_compare, vocabulary)
