import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.chat.service import ask, create_conversation, lookup_target, select_routes
from app.models import Base, Chunk, Document, DocumentVersion, Workspace
from app.retrieval.document_lookup import build_document_context, group_evidence_by_document
from app.retrieval.schemas import AnswerState, Evidence, RetrievalResult, RetrievalTrace


class StaticRetrievalRuntime:
    """Deterministic V1 retrieval seam for document-list presentation tests."""

    def __init__(self, evidence: tuple[Evidence, ...]) -> None:
        self.evidence = evidence

    def search(self, _session, _workspace_id, _query, *, final_evidence_limit=None):
        return RetrievalResult(
            self.evidence,
            AnswerState.GROUNDED,
            trace=RetrievalTrace(final_evidence_count=len(self.evidence)),
        )


LOOKUP_QUERIES = (
    "Hüseyin Hüsnü Subaşı hangi belgelerde geçmektedir?",
    "Ahmet Muhtar Merter hangi dosyalarda geçiyor?",
    "Beykoz geçen belgeleri listele.",
    "468 ada geçen belgeleri listele.",
    "Çekme Dalyanı geçtiği belgeler",
    "Veraset belgelerini listele.",
    "Tapu senedi belgelerini listele.",
    "documents containing Hüseyin Hüsnü Subaşı",
    "list documents mentioning Beykoz",
)


def test_planner_detects_document_lookup_patterns():
    for query in LOOKUP_QUERIES:
        selection = select_routes(query, "automatic")
        assert selection.intent == "entity_document_lookup", query
        assert selection.needs_list is True
        assert selection.routes == ("hybrid",)
    assert lookup_target(LOOKUP_QUERIES[0]) == "Hüseyin Hüsnü Subaşı"


def test_document_grouping_deduplicates_chunks_and_preserves_metadata():
    metadata = {
        "document_code": "B-2/ı",
        "title": "Tapu kaydı",
        "page": "3",
        "source_original": "B-2-ı.pdf",
        "document_type": "application/pdf",
    }
    evidence = [
        Evidence("w", "source", "Hüseyin malik.", 0.9, "d", "v", "c1", metadata=metadata),
        Evidence(
            "w", "source", "Hüseyin mal sahibi.", 0.8, "d", "v", "c2", metadata=metadata
        ),
    ]
    documents = group_evidence_by_document(evidence, exact_text="Hüseyin")
    assert len(documents) == 1
    assert [item.chunk_id for item in documents[0].matched_chunks] == ["c1", "c2"]
    assert "document_code: B-2/ı" in build_document_context(documents)
    assert "source_original: B-2-ı.pdf" in build_document_context(documents)


def test_chat_returns_one_concise_row_and_citation_per_document():
    session = sessionmaker(bind=create_engine("sqlite:///:memory:"))()
    Base.metadata.create_all(session.bind)
    now, workspace_id = datetime.now(UTC), str(uuid4())
    session.add(
        Workspace(
            id=workspace_id,
            slug="lookup",
            name="Lookup",
            state="active",
            created_at=now,
            updated_at=now,
        )
    )
    evidence: list[Evidence] = []
    for index, title in enumerate(("B-2/ı", "A-21/b")):
        document_id, version_id = str(uuid4()), str(uuid4())
        session.add(
            Document(
                id=document_id,
                workspace_id=workspace_id,
                title=title,
                active_version_id=version_id,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            DocumentVersion(
                id=version_id,
                workspace_id=workspace_id,
                document_id=document_id,
                version_number=1,
                source_hash=str(uuid4()),
                source_path=f"{title}.pdf",
                source_filename=f"{title}.pdf",
                mime_type="application/pdf",
                size_bytes=10,
                state="ready",
                created_at=now,
            )
        )
        # More chunks than the document limit verifies that one document cannot crowd
        # another document out of an entity-list result.
        for ordinal in range(55 if index == 0 else 1):
            chunk_id = str(uuid4())
            content = "Hüseyin Hüsnü Subaşı tapu kaydında mal sahibi olarak geçer."
            metadata = {
                "document_code": title,
                "title": title,
                "heading": "Tapu sahibi",
                "page": str(ordinal + 1),
            }
            session.add(
                Chunk(
                    id=chunk_id,
                    workspace_id=workspace_id,
                    document_id=document_id,
                    document_version_id=version_id,
                    ordinal=ordinal,
                    content=content,
                    content_hash=str(uuid4()),
                    metadata_json=json.dumps(metadata),
                    created_at=now,
                )
            )
            evidence.append(
                Evidence(
                    workspace_id,
                    title,
                    content,
                    1.0,
                    document_id,
                    version_id,
                    chunk_id,
                    metadata=metadata,
                )
            )
    session.commit()
    conversation = create_conversation(session, workspace_id, "Arama")
    _, answer, run = ask(
        session,
        workspace_id,
        conversation.id,
        "Hüseyin Hüsnü Subaşı hangi belgelerde geçmektedir?",
        "automatic",
        retrieval_runtime=StaticRetrievalRuntime(tuple(evidence)),
    )
    citations = json.loads(answer.citations_json)
    metadata = json.loads(answer.metadata_json)
    assert run.selected_routes_json == '["hybrid"]'
    assert metadata["intent"] == "entity_document_lookup"
    assert metadata["needs_list"] is True
    assert len(citations) == 2
    assert len({item["document_id"] for item in citations}) == 2
    assert answer.content.count("| B-2/ı |") == 1
    assert answer.content.count("| A-21/b |") == 1
    assert "Toplam: 2 belge" in answer.content
    assert len(answer.content) < 700
