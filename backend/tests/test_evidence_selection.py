from app.chat.evidence_selection import select_answer_evidence
from app.chat.execution import raw_evidence_guard
from app.chat.query_plan import QueryEntity, QueryPlan
from app.chat.service import _answer
from app.retrieval.schemas import Evidence


def _plan(operation="identify"):
    return QueryPlan(
        operation=operation,
        entities=(
            QueryEntity(
                "person",
                "Berke",
                "berke",
                "Mehmet Berke Merter",
                ("Berke", "Dr. Berke"),
                0.9,
            ),
        ),
    )


def test_identify_selector_promotes_full_name_and_rejects_weak_identity_evidence():
    candidates = [
        Evidence("w", "numeric", "Berke 16.833.948", 10, document_id="a", chunk_id="a"),
        Evidence(
            "w",
            "property",
            "Mehmet Berke Merter tapu kaydında taşınmaz hissedarı ve malik olarak geçmektedir.",
            2,
            document_id="b",
            chunk_id="b",
        ),
        Evidence(
            "w",
            "other",
            "Hasan Tahsin Merter için icra kaydı bulunmaktadır.",
            9,
            document_id="c",
            chunk_id="c",
        ),
        Evidence("w", "stub", "TGKM Başvuru Fişi", 8, document_id="d", chunk_id="d"),
    ]

    selected, trace = select_answer_evidence(candidates, _plan())

    assert [item.chunk_id for item in selected] == ["b"]
    assert trace["selected_count"] == 1
    items = {item["chunk_id"]: item for item in trace["items"]}
    assert "resolved_full_name" in items["b"]["signals"]
    assert "numeric_shorthand" in items["a"]["signals"]
    assert items["a"]["selected"] is False
    assert items["c"]["selected"] is False
    assert items["d"]["selected"] is False


def test_selector_uses_independent_documents_and_operation_limit(monkeypatch):
    candidates = [
        Evidence(
            "w",
            f"source-{index}",
            f"Mehmet Berke Merter tapuda hissedar ve malik olarak geçer {index}.",
            2,
            document_id=document_id,
            chunk_id=str(index),
        )
        for index, document_id in enumerate(("one", "one", "two", "three"), 1)
    ]
    settings = type(
        "S",
        (),
        {
            "identify_final_evidence_top_k": 2,
            "describe_final_evidence_top_k": 5,
            "timeline_final_evidence_top_k": 5,
            "final_evidence_top_k": 10,
        },
    )()
    monkeypatch.setattr("app.chat.evidence_selection.get_settings", lambda: settings)

    selected, trace = select_answer_evidence(candidates, _plan())

    assert [item.document_id for item in selected] == ["one", "two"]
    assert trace["limit"] == 2


def test_identify_fallback_and_citations_use_only_selected_evidence():
    candidates = [
        Evidence("w", "numeric", "Berke 16.833.948", 10, document_id="a", chunk_id="a"),
        Evidence(
            "w",
            "property",
            "Mehmet Berke Merter tapu kaydında taşınmaz hissedarıdır.",
            2,
            document_id="b",
            chunk_id="b",
        ),
    ]

    selected, _ = select_answer_evidence(candidates, _plan())
    answer, _, citations = _answer(selected, _plan())

    assert "Mehmet Berke Merter" in answer
    assert "16.833.948" not in answer
    assert "tapu kaydında taşınmaz hissedarıdır" not in answer
    assert answer.endswith("[1]")
    assert [citation["chunk_id"] for citation in citations] == ["b"]


def test_property_describe_fallback_uses_specific_selected_facts():
    plan = _plan("describe")
    evidence = [
        Evidence(
            "w",
            "one",
            "Mehmet Berke Merter 8 pafta 355 ada 248 parselde 219/800 hisse sahibidir.",
            2,
            document_id="a",
            chunk_id="a",
        ),
        Evidence(
            "w",
            "two",
            "Mehmet Berke Merter 40 pafta 303 ada 16 parselde 1/8 hisse ile geçer.",
            2,
            document_id="b",
            chunk_id="b",
        ),
        Evidence(
            "w",
            "three",
            "Mehmet Berke Merter 355 ada 17 parselde 1/2 hisse ile kaydedilmiştir.",
            2,
            document_id="c",
            chunk_id="c",
        ),
    ]

    answer, _, citations = _answer(evidence, plan)

    assert "248 parsel" in answer and "16 parsel" in answer and "17 parsel" in answer
    assert "güncel mülkiyet" in answer
    assert [item["chunk_id"] for item in citations] == ["a", "b", "c"]


def test_property_describe_does_not_render_legal_identifier_as_share():
    plan = _plan("describe")
    evidence = [
        Evidence(
            "w",
            "one",
            "Mehmet Berke Merter 40 pafta 303 ada 16 parsel. Karar No: 980/274",
            2,
            document_id="a",
            chunk_id="a",
        ),
    ]

    answer, _, _ = _answer(evidence, plan)

    assert "yerel bir mülkiyet ilişkisine" in answer
    assert "980/274 hisse" not in answer


def test_property_describe_rejects_unbound_property_and_keeps_bound_fact():
    plan = _plan("describe")
    evidence = [
        Evidence(
            "w",
            "bound",
            "40 pafta 303 ada 16 parsel, 9/64 hissesi Mehmet Berke Merter",
            2,
            document_id="a",
            chunk_id="a",
        ),
        Evidence(
            "w",
            "unbound",
            "Sarıyer-Kilyos 1 pafta 41 parsel Hasan Tahsin Merter varisleri",
            2,
            document_id="b",
            chunk_id="b",
        ),
    ]

    answer, _, citations = _answer(evidence, plan)

    assert "40 pafta, 303 ada, 16 parsel" in answer
    assert "1 pafta, 41 parsel" not in answer
    assert [item["chunk_id"] for item in citations] == ["a", "b"]


def test_raw_evidence_guard_detects_dump_but_allows_concise_paraphrase():
    source = (
        "nolu 2240 m2 miktarında kargir yanaşma odası ve taşocağı müştemil arazinin "
        "dokuz bölü altmış dört hissesi Mehmet Berke Merter adına kayıtlıdır"
    )
    dumped = f"Kaynak metni şöyledir: {source}. [1]"
    concise = "Mehmet Berke Merter, belgede taşınmaz hissedarı olarak geçiyor. [1]"

    assert raw_evidence_guard(dumped, [source]) is True
    assert raw_evidence_guard(concise, [source]) is False
