from app.query.briefing import (
    WorkspaceBriefing,
    WorkspaceEntityCandidate,
    resolve_workspace_entities,
)
from app.query.ir import IRVocabulary, lower_semantic_understanding, validate_logical_ir
from app.query.understanding import SemanticEntity, SemanticTarget, SemanticUnderstanding


def _understanding(mention="Tahsin Merter"):
    return SemanticUnderstanding(
        state="unresolved",
        entities=(
            SemanticEntity(
                reference_id="person-1",
                mention=mention,
                entity_type="person",
                resolution="unresolved",
            ),
        ),
        unresolved_questions=("Which person is meant?",),
        confidence=0.5,
    )


def test_workspace_briefing_resolves_one_exact_workspace_candidate():
    result = resolve_workspace_entities(
        _understanding(),
        WorkspaceBriefing(
            workspace_id="workspace-a",
            generation_id="generation-a",
            entities=(
                WorkspaceEntityCandidate("entity-a", "person", "Tahsin Merter"),
            ),
        ),
    )

    assert result.state == "resolved"
    assert result.entities[0].canonical_entity_id == "entity-a"


def test_workspace_briefing_keeps_multiple_exact_candidates_unresolved():
    result = resolve_workspace_entities(
        _understanding("Merter"),
        WorkspaceBriefing(
            workspace_id="workspace-a",
            generation_id="generation-a",
            entities=(
                WorkspaceEntityCandidate("entity-a", "person", "Tahsin Merter", ("Merter",)),
                WorkspaceEntityCandidate("entity-b", "person", "Rauf Merter", ("Merter",)),
            ),
        ),
    )

    assert result.state == "unresolved"
    assert result.entities[0].canonical_entity_id is None
    assert "Multiple canonical identities" in result.unresolved_questions[-1]


def test_collision_keeps_identity_unresolved_but_allows_literal_grounded_description():
    understood = SemanticUnderstanding(
        state="unresolved",
        entities=(
            SemanticEntity(
                reference_id="person-1",
                mention="Merter",
                entity_type="person",
                resolution="unresolved",
            ),
        ),
        targets=(
            SemanticTarget(target_type="entity", reference_id="person-1", description="person"),
        ),
        operators=("describe", "retrieve_evidence"),
        coverage="relevant_evidence",
        unresolved_questions=("Which person is meant?",),
        confidence=0.5,
    )
    resolved = resolve_workspace_entities(
        understood,
        WorkspaceBriefing(
            workspace_id="workspace-a",
            generation_id="generation-a",
            entities=(
                WorkspaceEntityCandidate("entity-a", "person", "Tahsin Merter", ("Merter",)),
                WorkspaceEntityCandidate("entity-b", "person", "Rauf Merter", ("Merter",)),
            ),
        ),
    )

    ir = lower_semantic_understanding(resolved, "workspace-a")

    assert resolved.state == "unresolved"
    assert resolved.entities[0].canonical_entity_id is None
    assert [node.kind for node in ir.nodes] == ["retrieve_evidence", "summarize"]
    assert validate_logical_ir(ir, IRVocabulary.core()) is ir
