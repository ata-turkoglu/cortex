"""Resume-safe section drafting with model work outside SQLite transactions."""

from .schemas import CompositionCheckpoint, SectionComposer
from .store import load_composition_run, save_composition_run


def draft_next_section(
    run_id: str, workspace_id: str, session_factory, composer: SectionComposer
) -> CompositionCheckpoint:
    session = session_factory()
    try:
        checkpoint, revision = load_composition_run(session, workspace_id, run_id)
        pending = next(
            (
                outline
                for outline in checkpoint.outline
                if not any(
                    section.section_id == outline.section_id
                    for section in checkpoint.sections
                )
            ),
            None,
        )
        if pending is None:
            return checkpoint
        drafting = checkpoint.model_copy(update={"state": "drafting"})
        revision = save_composition_run(session, drafting, expected_revision=revision)
        session.commit()
        title, evidence_ids = drafting.title, drafting.evidence_ids
    finally:
        session.close()
    # External composition receives a detached outline/evidence-ID snapshot only.
    section = composer.draft(title, pending, evidence_ids)
    if section.section_id != pending.section_id:
        raise ValueError("composer returned a different outline section")
    validated = section.model_copy(update={
        "state": "validated" if not section.consistency_issues else "failed"
    })
    updated = drafting.model_copy(update={
        "sections": (*drafting.sections, validated),
        "state": "validating" if validated.state == "validated" else "failed",
        "validation_issues": validated.consistency_issues,
    })
    session = session_factory()
    try:
        save_composition_run(session, updated, expected_revision=revision)
        session.commit()
    finally:
        session.close()
    return updated


def assemble_final(checkpoint: CompositionCheckpoint) -> CompositionCheckpoint:
    if not checkpoint.outline or len(checkpoint.sections) != len(checkpoint.outline):
        raise ValueError("every outline section must be drafted before assembly")
    if checkpoint.validation_issues or any(
        section.state != "validated" for section in checkpoint.sections
    ):
        raise ValueError("composition contains unresolved validation issues")
    ordered = sorted(
        checkpoint.sections,
        key=lambda item: next(
            outline.order for outline in checkpoint.outline
            if outline.section_id == item.section_id
        ),
    )
    outline_by_id = {item.section_id: item for item in checkpoint.outline}
    parts = [f"# {checkpoint.title}"]
    lineage = {}
    for section in ordered:
        parts.append(f"## {outline_by_id[section.section_id].title}")
        for paragraph in section.paragraphs:
            parts.append(" ".join(sentence.text for sentence in paragraph.sentences))
            for sentence in paragraph.sentences:
                lineage[sentence.sentence_id] = sentence.evidence_ids
    from .schemas import FinalArtifact

    artifact = FinalArtifact(
        title=checkpoint.title, markdown="\n\n".join(parts), sentence_evidence=lineage
    )
    ready = checkpoint.model_copy(update={"state": "ready", "final_artifact": artifact})
    return CompositionCheckpoint.model_validate(ready.model_dump())
