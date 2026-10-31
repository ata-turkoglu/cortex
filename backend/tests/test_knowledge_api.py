from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.knowledge import (
    AliasCurationRequest,
    MergeCurationRequest,
    SplitCurationRequest,
    SplitPartitionRequest,
    add_alias,
    cutover_status,
    entity_evidence,
    generation_readiness,
    identity_history,
    list_entities,
    merge_entities,
    split_entity,
)
from app.knowledge import KnowledgeAuthority, new_canonical_id
from app.knowledge.entities import IdentityDecisionKind, IdentityOperation
from app.knowledge.graph import CanonicalEntityView, EntityEvidenceView, IdentityHistoryView
from app.models import (
    Base,
    KnowledgeGeneration,
    KnowledgeStageState,
    QueryCutoverAttempt,
    QueryRuntimeActivation,
    Workspace,
)


class FakeGraph:
    def __init__(self):
        self.calls = []
        self.entity_id = new_canonical_id()
        self.other_id = new_canonical_id()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def list_canonical_entities(self, limit):
        self.calls.append(("list", limit))
        return (
            CanonicalEntityView(
                self.entity_id,
                "person",
                "Ayşe Yılmaz",
                None,
                "user_curated",
                "active",
                ("A. Yılmaz",),
            ),
        )

    def entity_evidence(self, entity_id, limit):
        self.calls.append(("evidence", entity_id, limit))
        return (
            EntityEvidenceView(
                new_canonical_id(),
                new_canonical_id(),
                "Ayşe",
                "document-a",
                "version-a",
                "logical-a",
                "chunk-a",
                3,
                7,
                "Ayşe",
                "run-a",
                "openai",
                "model-a",
                "prompt-v1",
                "schema-v1",
                0.9,
                "validated",
                "generation-a",
            ),
        )

    def identity_history(self, limit):
        self.calls.append(("history", limit))
        return (
            IdentityHistoryView(
                new_canonical_id(),
                "merge",
                "user_curated",
                (self.entity_id, self.other_id),
                (self.entity_id,),
                (),
                "reviewed",
                {},
            ),
        )

    def _operation(self, kind, source, result, reason, details=None):
        return IdentityOperation(
            new_canonical_id(),
            kind,
            KnowledgeAuthority.USER_CURATED,
            source,
            result,
            (),
            reason,
            details or {},
        )

    def add_alias(self, entity_id, value, reason):
        self.calls.append(("alias", entity_id, value, reason))
        return self._operation(
            IdentityDecisionKind.ALIAS_ADD,
            (entity_id,),
            (entity_id,),
            reason,
            {"value": value},
        )

    def merge_canonical_entities(
        self, primary_entity_id, merged_entity_ids, *, evidence_ids, reason
    ):
        self.calls.append(("merge", primary_entity_id, merged_entity_ids, evidence_ids, reason))
        return self._operation(
            IdentityDecisionKind.MERGE,
            (primary_entity_id, *merged_entity_ids),
            (primary_entity_id,),
            reason,
        )

    def split_canonical_entity(
        self, entity_id, partitions, *, evidence_ids, reason
    ):
        self.calls.append(("split", entity_id, partitions, evidence_ids, reason))
        results = tuple(new_canonical_id() for _ in partitions)
        return self._operation(IdentityDecisionKind.SPLIT, (entity_id,), results, reason)


def test_curation_api_exposes_entities_evidence_history_and_reversible_commands(monkeypatch):
    graph = FakeGraph()
    monkeypatch.setattr("app.api.knowledge._workspace_graph", lambda *_: graph)
    session = object()

    entities = list_entities("workspace-a", 25, session)
    evidence = entity_evidence("workspace-a", graph.entity_id, 20, session)
    history = identity_history("workspace-a", 30, session)
    alias = add_alias(
        "workspace-a",
        graph.entity_id,
        AliasCurationRequest(value="A. Yılmaz", reason="reviewed"),
        session,
    )
    merge = merge_entities(
        "workspace-a",
        MergeCurationRequest(
            primary_entity_id=graph.entity_id,
            merged_entity_ids=[graph.other_id],
            reason="same person",
        ),
        session,
    )
    split = split_entity(
        "workspace-a",
        graph.entity_id,
        SplitCurationRequest(
            partitions=[
                SplitPartitionRequest(display_name="Ayşe", mention_ids=[new_canonical_id()]),
                SplitPartitionRequest(display_name="Aylin", mention_ids=[new_canonical_id()]),
            ],
            reason="different people",
        ),
        session,
    )

    assert entities[0].authority == "user_curated"
    assert evidence[0].source_text == "Ayşe"
    assert history[0].kind == "merge"
    assert alias.kind == "alias_add"
    assert merge.kind == "merge"
    assert split.kind == "split"


def test_readiness_api_lists_workspace_generation_checkpoints(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    timestamp = datetime.now(UTC)
    workspace_id, generation_id = str(uuid4()), str(uuid4())
    session.add(
        Workspace(
            id=workspace_id, slug="readiness", name="Readiness", state="active",
            created_at=timestamp, updated_at=timestamp,
        )
    )
    session.add(
        KnowledgeGeneration(
            id=generation_id, workspace_id=workspace_id, source_fingerprint="source",
            state="active", failure_json=None, created_at=timestamp, updated_at=timestamp,
            activated_at=timestamp,
        )
    )
    session.add(
        KnowledgeStageState(
            id=str(uuid4()), workspace_id=workspace_id, generation_id=generation_id,
            stage="source_relational", state="ready", input_fingerprint="source",
            output_fingerprint="source", metrics_json='{"chunk_count": 19}', error_json=None,
            updated_at=timestamp,
        )
    )
    session.commit()
    monkeypatch.setattr("app.api.knowledge.WorkspaceContext.load", lambda *_: object())

    result = generation_readiness(workspace_id, 20, session)

    assert result[0].state == "active"
    assert result[0].stages[0].metrics == {"chunk_count": 19}


def test_cutover_status_defaults_to_v1_and_exposes_workspace_audit(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    timestamp = datetime.now(UTC)
    workspace_id, generation_id = str(uuid4()), str(uuid4())
    session.add(
        Workspace(
            id=workspace_id,
            slug="cutover",
            name="Cutover",
            state="active",
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    session.add(
        KnowledgeGeneration(
            id=generation_id,
            workspace_id=workspace_id,
            source_fingerprint="source",
            state="active",
            failure_json=None,
            created_at=timestamp,
            updated_at=timestamp,
            activated_at=timestamp,
        )
    )
    session.add(
        QueryRuntimeActivation(
            workspace_id=workspace_id,
            runtime_version="v2",
            generation_id=generation_id,
            source_fingerprint="source",
            evaluation_fingerprint="evaluation",
            curation_fingerprint="curation",
            activated_at=timestamp,
            updated_at=timestamp,
        )
    )
    session.add(
        QueryCutoverAttempt(
            id=str(uuid4()),
            workspace_id=workspace_id,
            generation_id=generation_id,
            state="activated",
            report_json='{"state": "activated"}',
            created_at=timestamp,
            finished_at=timestamp,
        )
    )
    session.commit()
    monkeypatch.setattr("app.api.knowledge.WorkspaceContext.load", lambda *_: object())

    result = cutover_status(workspace_id, 20, session)

    assert result.runtime_version == "v2"
    assert result.generation_id == generation_id
    assert result.attempts[0].report == {"state": "activated"}
