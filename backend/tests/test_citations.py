from app.chat.execution import finalize_citations


def test_final_citations_prune_unused_and_renumber_in_answer_order():
    citations = [
        {"document_id": "a", "chunk_id": "a", "label": "A"},
        {"document_id": "b", "chunk_id": "b", "label": "B"},
        {"document_id": "c", "chunk_id": "c", "label": "C"},
        {"document_id": "d", "chunk_id": "d", "label": "D"},
        {"document_id": "e", "chunk_id": "e", "label": "E"},
    ]

    answer, final = finalize_citations("Birinci [1], üçüncü [3], beşinci [5].", citations) or (
        "",
        [],
    )

    assert answer.endswith("[1], üçüncü [2], beşinci [3].")
    assert [item["chunk_id"] for item in final] == ["a", "c", "e"]


def test_final_citations_reject_missing_or_invented_markers():
    citations = [{"document_id": "a", "chunk_id": "a", "label": "A"}]

    assert finalize_citations("Desteksiz yanıt.", citations) is None
    assert finalize_citations("Uydurma [2].", citations) is None
