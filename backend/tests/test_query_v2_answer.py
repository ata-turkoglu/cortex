from app.query.answer import AnswerEngine
from app.query.orchestration import (
    CanonicalEventResult,
    CompletenessEvidenceRef,
    CompletenessReport,
    MaterializedCitation,
    QueryCompleteness,
    ReasoningPackage,
    ResultAmbiguity,
)


def _package(**changes):
    values = {
        "workspace_id": "workspace-a",
        "generation_id": "generation-a",
        "state": "unsupported",
        "completeness": CompletenessReport(coverage="grounded", state="unknown"),
        "confidence": 0.0,
    }
    values.update(changes)
    return ReasoningPackage(**values)


def test_answer_engine_keeps_unsupported_fail_closed():
    draft = AnswerEngine().render(_package())

    assert draft.state == "unsupported"
    assert "yeterli doğrulanmış kanıt" in draft.content
    assert draft.citations == ()


def test_answer_engine_renders_generic_typed_insufficient_evidence_reason():
    draft = AnswerEngine().render(_package(failure_reason="insufficient_evidence"))

    assert "yeterli doğrulanmış kanıt" in draft.content
    assert draft.metadata["reason_code"] == "insufficient_evidence"


def test_answer_engine_renders_capability_unavailable_as_normal_v2_unsupported_answer():
    draft = AnswerEngine().render(
        _package(issues=("capability_unavailable:no ready canonical capability",))
    )

    assert draft.state == "unsupported"
    assert "sorgu türü" in draft.content
    assert draft.citations == ()


def test_answer_engine_requires_clarification_for_ambiguity():
    draft = AnswerEngine().render(
        _package(
            state="ambiguous",
            ambiguities=(
                ResultAmbiguity(
                    ambiguity_id="ambiguous-person",
                    reason="two canonical people match the name",
                    candidate_ids=("entity-a", "entity-b"),
                ),
            ),
        )
    )

    assert draft.state == "ambiguous"
    assert "tek bir anlama" in draft.content
    assert "two canonical people" not in draft.content


def test_answer_engine_renders_typed_canonical_events():
    draft = AnswerEngine().render(
        _package(
            state="grounded",
            confidence=0.9,
            events=(
                CanonicalEventResult(
                    item_id="event-1",
                    event_id="event-1",
                    event_type="historical_event",
                    event_name="E1",
                    event_date="1974-06-12",
                    participant_canonical_ids=("person-1",),
                    workspace_id="workspace-a",
                    generation_id="generation-a",
                    values={},
                    evidence_ids=("evidence-1",),
                ),
            ),
        )
    )

    assert "1974-06-12: E1 (historical_event)" in draft.content
    assert "person-1" in draft.content


def test_answer_engine_renders_authoritative_structured_analytics_without_recomputation():
    draft = AnswerEngine().render(
        _package(
            state="grounded",
            confidence=0.9,
            structured_rows=(
                {
                    "item_id": "surname-merter",
                    "values": {"surname": "Merter", "confirmed_count": 2},
                    "evidence_ids": ("evidence-1",),
                },
                {
                    "item_id": "comparison",
                    "values": {"result": {"left": 2, "right": 1}},
                    "evidence_ids": ("evidence-1",),
                },
            ),
        )
    )

    assert "surname: Merter, confirmed_count: 2" in draft.content
    assert "result: {'left': 2, 'right': 1}" in draft.content


def test_answer_engine_renders_partial_canonical_count_without_claiming_exactness():
    draft = AnswerEngine().render(
        _package(
            state="partial",
            confidence=1.0,
            aggregates=(
                {
                    "item_id": "count",
                    "values": {"result": 3},
                    "evidence_ids": ("evidence-1",),
                    "function": "count",
                    "value": 3,
                    "population_count": 3,
                },
            ),
            completeness=CompletenessReport(
                coverage="exhaustive",
                state="partial",
                boundary="Person surname = Merter",
                generation_id="generation-a",
                candidate_count=3,
                processed_count=3,
                confirmed_count=3,
                query=QueryCompleteness(
                    status="PARTIAL",
                    scope="Person surname = merter",
                    reasons=("Unresolved Person evidence may change the canonical population.",),
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
                    known_count=3,
                    min_count=3,
                    additional_population_possible=True,
                ),
            ),
        )
    )

    assert "kesin olarak 3 kişi" in draft.content
    assert "kısmi" in draft.content
    assert "Bay H. Tahsin Merter" in draft.content


def _citation(evidence_id: str, text: str, rank: int) -> MaterializedCitation:
    return MaterializedCitation(
        citation_id=f"citation-{evidence_id}",
        evidence_id=evidence_id,
        document_id=f"document-{rank}",
        document_version_id=f"version-{rank}",
        logical_document_id=f"logical-{rank}",
        chunk_id=f"chunk-{rank}",
        start_offset=0,
        end_offset=len(text),
        source_text=text,
        label=f"Kaynak {rank}",
        rank=rank,
        score=0.9,
        supporting_step_ids=("execute.retrieve",),
    )


def test_answer_engine_summarizes_retrieval_evidence_without_internal_metadata():
    long_evidence = (
        "Hasan Tahsin Merter, 40 pafta 303 ada 16 parsel numaralı taşınmazla ilgili "
        "tapu kaydında geçmektedir. " + "Ek ayrıntı. " * 100
    )
    draft = AnswerEngine().render(
        _package(
            state="grounded",
            confidence=0.9,
            structured_rows=(
                {
                    "item_id": "retrieval-row-1",
                    "values": {"evidence": long_evidence, "fusion_rank": 1},
                    "evidence_ids": ("evidence-1",),
                },
                {
                    "item_id": "retrieval-row-2",
                    "values": {"evidence": "Başka kayıt.", "fusion_rank": 2},
                    "evidence_ids": ("evidence-2",),
                },
            ),
            citations=(
                _citation("evidence-1", long_evidence, 1),
                _citation("evidence-2", "Başka kayıt.", 2),
            ),
        )
    )

    assert "Doğrulanmış arşiv kaynaklarında" in draft.content
    assert "40 pafta 303 ada 16 parsel" in draft.content
    assert "Based on the validated evidence" not in draft.content
    assert all(
        term not in draft.content
        for term in (
            "evidence:",
            "fusion_rank",
            "dense_rank",
            "sparse_rank",
            "EngineResult",
            "ReasoningPackage",
        )
    )
    assert len(draft.content) < 700
    assert len(draft.citations) == 2


def test_answer_engine_uses_typed_identity_failure_reason():
    draft = AnswerEngine().render(_package(failure_reason="identity_unresolved"))

    assert "kanonik kimlik kaydı" in draft.content
    assert draft.metadata["reason_code"] == "identity_unresolved"


def test_retrieval_excerpt_prefers_the_sentence_that_matches_the_query():
    excerpt = AnswerEngine._safe_excerpt(
        "The cobalt orchard archive proves the river allotment. "
        "Rare lexical marker zephyr-741 belongs to the validated deed.",
        "Describe the deed with zephyr-741 evidence",
    )

    assert excerpt == "Rare lexical marker zephyr-741 belongs to the validated deed."
    assert AnswerEngine._safe_excerpt("First sentence. Second sentence.") == "First sentence."
