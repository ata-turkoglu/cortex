from app.query.answer import AnswerEngine
from app.query.orchestration import (
    AggregateResult,
    CompletenessEvidenceRef,
    CompletenessReport,
    QueryCompleteness,
    ReasoningPackage,
)
from app.query.presentation import (
    CanonicalPersonDisplayGroup,
    build_canonical_person_presentations,
    group_canonical_person_presentations,
)


def _person(entity_id: str, display_name: str, *, property_count: int | None = None):
    values = {
        "entity_id": entity_id,
        "entity_type": "person",
        "display_name": display_name,
    }
    if property_count is not None:
        values["property_count"] = property_count
    return {"item_id": entity_id, "values": values, "evidence_ids": ("evidence-1",)}


def _partial_person_package(rows):
    return ReasoningPackage(
        workspace_id="workspace-a",
        generation_id="generation-a",
        state="partial",
        confidence=1.0,
        structured_rows=rows,
        completeness=CompletenessReport(
            coverage="exhaustive",
            state="partial",
            boundary="Person surname = Merter",
            generation_id="generation-a",
            candidate_count=len(rows),
            processed_count=len(rows),
            confirmed_count=len(rows),
            query=QueryCompleteness(
                status="PARTIAL",
                scope="Person surname = merter",
                relevant_unresolved_count=1,
                affected_dimensions=("population", "count"),
                evidence_refs=(
                    CompletenessEvidenceRef(
                        evidence_id="mention-1",
                        kind="unresolved_person",
                        raw_text="Bay H. Tahsin Merter",
                        document_id="document-1",
                        document_version_id="version-1",
                        logical_document_id="logical-1",
                        chunk_id="chunk-1",
                        start_offset=0,
                        end_offset=20,
                    ),
                ),
                known_count=len(rows),
                min_count=len(rows),
                additional_population_possible=True,
            ),
        ),
    )


def test_canonical_person_presentations_mark_identical_names_as_unresolved_candidates():
    package = _partial_person_package(
        (
            _person("person-b", "Tahsin Merter"),
            _person("person-a", "Tahsin Merter"),
            _person("person-d", "RAUF MERTER"),
            _person("person-c", "rauf merter"),
            _person("person-e", "Rauf Merter"),
        )
    )

    labels = build_canonical_person_presentations(package.structured_rows)

    assert [labels[item].display_label for item in ("person-a", "person-b")] == [
        "Tahsin Merter (kimlik adayı 1/2)",
        "Tahsin Merter (kimlik adayı 2/2)",
    ]
    assert [labels[item].display_label for item in ("person-c", "person-d", "person-e")] == [
        "Rauf Merter (kimlik adayı 1/3)",
        "Rauf Merter (kimlik adayı 2/3)",
        "Rauf Merter (kimlik adayı 3/3)",
    ]
    assert labels["person-d"].original_preferred_name == "RAUF MERTER"
    assert labels == build_canonical_person_presentations(package.structured_rows)
    assert group_canonical_person_presentations(package.structured_rows) == (
        CanonicalPersonDisplayGroup("Tahsin Merter", ("person-b", "person-a")),
        CanonicalPersonDisplayGroup("Rauf Merter", ("person-d", "person-c", "person-e")),
    )


def test_answer_engine_groups_mixed_collisions_without_merging_and_preserves_blocker():
    draft = AnswerEngine().render(
        _partial_person_package(
            (
                _person("tahsin-b", "Tahsin Merter"),
                _person("tahsin-a", "Tahsin Merter"),
                _person("mustafa", "Mustafa Merter"),
                _person("rauf-c", "RAUF MERTER"),
                _person("rauf-a", "Rauf Merter"),
                _person("rauf-b", "RAUF MERTER"),
            )
        )
    )

    assert "6 kimlik adayı ve 3 farklı kişi adı görünümü" in draft.content
    assert "Mustafa Merter" in draft.content
    assert "Tahsin Merter — 2 ayrı kanonik kimlik adayı" in draft.content
    assert "Rauf Merter — 3 ayrı kanonik kimlik adayı" in draft.content
    assert "aynı kişi olduklarını doğrulayan yeterli kanıt yok" in draft.content
    assert "Bay H. Tahsin Merter" in draft.content
    assert len(draft.metadata["canonical_person_presentations"]) == 6


def test_answer_engine_keeps_rank_metrics_per_canonical_person():
    draft = AnswerEngine().render(
        _partial_person_package(
            (
                _person("rauf-b", "RAUF MERTER", property_count=1),
                _person("rauf-a", "Rauf Merter", property_count=2),
            )
        )
    )

    assert "Rauf Merter (kimlik adayı 1/2) — 2 taşınmaz kaydı" in draft.content
    assert "Rauf Merter (kimlik adayı 2/2) — 1 taşınmaz kaydı" in draft.content


def test_answer_engine_does_not_change_authoritative_count_for_colliding_names():
    package = _partial_person_package(
        tuple(_person(f"person-{index}", "Tahsin Merter") for index in range(6))
    )
    package = package.model_copy(
        update={
            "structured_rows": (),
            "aggregates": (
                AggregateResult(
                    item_id="count",
                    values={"result": 6},
                    evidence_ids=("evidence-1",),
                    function="count",
                    value=6,
                    population_count=6,
                ),
            ),
        }
    )

    draft = AnswerEngine().render(package)

    assert "kesin olarak 6 kişi" in draft.content
