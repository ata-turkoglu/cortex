from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Workspace
from app.query.orchestration.schemas import (
    CompletenessReport,
    MaterializedCitation,
    ReasoningPackage,
)
from app.reasoning.composition import (
    CompositionCheckpoint,
    DraftSection,
    GroundedParagraph,
    GroundedSentence,
    OutlineSection,
    assemble_final,
    create_composition_run,
    draft_next_section,
    load_composition_run,
    save_composition_run,
)
from app.reasoning.research import (
    CrossSourceClaim,
    ResearchDecomposition,
    ResearchSubquery,
    collect_evidence,
    create_research_run,
    execute_decomposition,
    finalize_research,
    load_research_run,
    save_research_run,
)


def database():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    session = factory()
    now = datetime.now(UTC)
    workspace_ids = (str(uuid4()), str(uuid4()))
    session.add_all(
        Workspace(id=value, slug=f"workspace-{index}", name=f"Workspace {index}",
                  state="active", created_at=now, updated_at=now)
        for index, value in enumerate(workspace_ids)
    )
    session.commit()
    session.close()
    return factory, workspace_ids


def package(workspace_id: str, generation_id: str, evidence_id: str) -> ReasoningPackage:
    return ReasoningPackage(
        workspace_id=workspace_id,
        generation_id=generation_id,
        state="grounded",
        citations=(MaterializedCitation(
            citation_id=f"citation-{evidence_id}", evidence_id=evidence_id,
            document_id="document", document_version_id="version",
            logical_document_id="logical", chunk_id="chunk", start_offset=0,
            end_offset=4, source_text="text", label="Document", rank=1, score=0.9,
            supporting_step_ids=("evidence.step",),
        ),),
        completeness=CompletenessReport(coverage="grounded", state="partial"),
        confidence=0.8,
    )


def test_research_decomposes_outside_transaction_and_is_workspace_isolated():
    factory, (workspace_id, other_workspace) = database()
    session = factory()
    checkpoint = create_research_run(
        session, workspace_id, "Write an archive history", generation_id="generation-a"
    )
    session.commit()
    session.close()

    class Planner:
        def decompose(self, goal, planned_workspace):
            assert goal == checkpoint.goal
            assert planned_workspace == workspace_id
            return ResearchDecomposition(
                subqueries=(
                    ResearchSubquery(
                        subquery_id="origins", question="What are the origins?",
                        purpose="Establish chronology",
                    ),
                    ResearchSubquery(
                        subquery_id="impact", question="What changed?",
                        purpose="Compare outcomes", depends_on=("origins",),
                    ),
                ),
                reasoning_strategy="Chronology followed by cross-source comparison",
            )

    planned = execute_decomposition(checkpoint.run_id, workspace_id, factory, Planner())
    assert planned.state == "planned"
    assert len(planned.decomposition.subqueries) == 2
    session = factory()
    with pytest.raises(LookupError):
        load_research_run(session, other_workspace, checkpoint.run_id)


def test_research_ready_state_requires_cross_source_evidence_lineage():
    factory, (workspace_id, _) = database()
    session = factory()
    checkpoint = create_research_run(
        session, workspace_id, "Compare sources", generation_id="generation-a"
    )
    session.commit()
    session.close()
    first = ResearchSubquery(
        subquery_id="first", question="First source?", purpose="Collect first account",
    )
    second = ResearchSubquery(
        subquery_id="second", question="Second source?", purpose="Collect corroboration",
        depends_on=("first",),
    )
    checkpoint = checkpoint.model_copy(update={
        "state": "planned",
        "decomposition": ResearchDecomposition(
            subqueries=(first, second), reasoning_strategy="Reconcile both accounts"
        ),
    })
    checkpoint = collect_evidence(
        checkpoint, "first", package(workspace_id, "generation-a", "evidence-a")
    )
    checkpoint = collect_evidence(
        checkpoint, "second", package(workspace_id, "generation-a", "evidence-b")
    )
    ready = finalize_research(
        checkpoint,
        (CrossSourceClaim(
            claim_id="claim-a", statement="The accounts corroborate the change.",
            kind="finding", evidence_ids=("evidence-a", "evidence-b"),
            source_subquery_ids=("first", "second"), confidence=0.8,
        ),),
    )
    session = factory()
    _, revision = load_research_run(session, workspace_id, checkpoint.run_id)
    save_research_run(session, ready, expected_revision=revision)
    with pytest.raises(RuntimeError, match="revision conflict"):
        save_research_run(session, ready, expected_revision=revision)


def test_composition_resumes_by_section_and_preserves_sentence_provenance():
    factory, (workspace_id, _) = database()
    session = factory()
    research = create_research_run(session, workspace_id, "Compose", generation_id="generation-a")
    session.commit()
    composition = create_composition_run(
        session, workspace_id, research.run_id, "Archive Book", ("evidence-a", "evidence-b")
    )
    outline = (
        OutlineSection(section_id="origins", title="Origins", objective="Explain origins", order=1),
        OutlineSection(section_id="impact", title="Impact", objective="Explain impact", order=2),
    )
    composition = composition.model_copy(update={"state": "drafting", "outline": outline})
    _, revision = load_composition_run(session, workspace_id, composition.run_id)
    save_composition_run(session, composition, expected_revision=revision)
    session.commit()
    session.close()

    class Composer:
        def draft(self, _title, section, evidence_ids):
            evidence_id = evidence_ids[0] if section.section_id == "origins" else evidence_ids[1]
            return DraftSection(
                section_id=section.section_id,
                state="drafted",
                paragraphs=(GroundedParagraph(
                    paragraph_id=f"paragraph-{section.section_id}",
                    sentences=(GroundedSentence(
                        sentence_id=f"sentence-{section.section_id}",
                        text=f"Grounded {section.title}.", evidence_ids=(evidence_id,),
                    ),),
                ),),
            )

    first = draft_next_section(composition.run_id, workspace_id, factory, Composer())
    assert [item.section_id for item in first.sections] == ["origins"]
    second = draft_next_section(composition.run_id, workspace_id, factory, Composer())
    final = assemble_final(second)
    assert final.state == "ready"
    assert final.final_artifact.sentence_evidence == {
        "sentence-origins": ("evidence-a",), "sentence-impact": ("evidence-b",)
    }

    session = factory()
    _, revision = load_composition_run(session, workspace_id, final.run_id)
    save_composition_run(session, final, expected_revision=revision)
    session.commit()
    resumed = draft_next_section(final.run_id, workspace_id, factory, Composer())
    assert resumed.final_artifact == final.final_artifact


def test_composition_rejects_uncollected_sentence_evidence():
    with pytest.raises(ValidationError, match="uncollected evidence"):
        CompositionCheckpoint(
            run_id="composition", research_run_id="research", workspace_id="workspace",
            title="Title", evidence_ids=("known",),
            outline=(OutlineSection(
                section_id="section", title="Section", objective="Objective", order=1
            ),),
            sections=(DraftSection(
                section_id="section", state="validated",
                paragraphs=(GroundedParagraph(
                    paragraph_id="paragraph",
                    sentences=(GroundedSentence(
                        sentence_id="sentence", text="Unsupported.",
                        evidence_ids=("unknown",),
                    ),),
                ),),
            ),),
        )
