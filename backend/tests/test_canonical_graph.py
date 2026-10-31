from app.knowledge import KnowledgeAuthority, new_canonical_id
from app.knowledge.claims import ClaimStage, KnowledgeClaim, link_contradiction
from app.knowledge.entities import (
    CanonicalEntity,
    EntityAlias,
    EntityMention,
    EntityType,
    IdentityDecisionKind,
    IdentityOperation,
)
from app.knowledge.graph import Neo4jGraphAdapter
from app.knowledge.provenance import ExactSourceProvenance


class ConsumedResult:
    def consume(self):
        return None


class RecordingTransaction:
    def __init__(self):
        self.calls = []

    def run(self, query, **parameters):
        self.calls.append((query, parameters))
        return ConsumedResult()


class RecordingSession:
    def __init__(self, driver, database):
        self.driver = driver
        self.database = database

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def execute_write(self, callback, *args, **kwargs):
        transaction = RecordingTransaction()
        callback(transaction, *args, **kwargs)
        self.driver.transactions.append((self.database, transaction.calls))


class RecordingDriver:
    def __init__(self):
        self.transactions = []
        self.query_results = []
        self.query_calls = []

    def session(self, *, database):
        return RecordingSession(self, database)

    def execute_query(self, query, **parameters):
        self.query_calls.append((query, parameters))
        records = self.query_results.pop(0) if self.query_results else []
        return (records, None, [])

    def close(self):
        pass


def provenance(workspace_id="workspace-a"):
    return ExactSourceProvenance(
        workspace_id=workspace_id,
        document_id="document-a",
        document_version_id="version-a",
        logical_document_id="logical-a",
        chunk_id="chunk-a",
        start_offset=4,
        end_offset=10,
        source_text="Ankara",
        extraction_run_id="run-a",
        provider="openai",
        model="model-a",
        prompt_version="prompt-v1",
        schema_version="schema-v1",
        confidence=0.9,
        validation_state="validated",
        generation="generation-a",
    )


def test_canonical_upsert_is_workspace_scoped_precedence_guarded_and_exactly_provenanced():
    driver = RecordingDriver()
    adapter = Neo4jGraphAdapter("workspace-a", driver)
    alias = EntityAlias(new_canonical_id(), "Ankara şehri", KnowledgeAuthority.VALIDATED)
    item = EntityMention(
        new_canonical_id(), "Ankara", EntityType.LOCATION, provenance()
    )
    entity = CanonicalEntity.create(
        EntityType.LOCATION,
        "Ankara",
        KnowledgeAuthority.VALIDATED,
        aliases=(alias,),
        mentions=(item,),
    )

    adapter.upsert_canonical_entity(entity, "generation-a")

    _, calls = driver.transactions[0]
    assert len(calls) == 3
    assert all(parameters["workspace_id"] == "workspace-a" for _, parameters in calls)
    node_query, node_parameters = calls[0]
    assert "CanonicalKnowledge:CanonicalEntity" in node_query
    assert "coalesce(n.authority_rank, 0) <= $authority_rank" in node_query
    assert node_parameters["authority_rank"] == int(KnowledgeAuthority.VALIDATED)
    provenance_query, provenance_parameters = calls[2]
    for label in (
        "CortexWorkspace",
        "CortexDocument",
        "CortexDocumentVersion",
        "CortexLogicalDocument",
        "CortexChunk",
        "CortexEvidence",
        "CortexMention",
    ):
        assert label in provenance_query
    payload = provenance_parameters["mentions"][0]
    assert payload["source_text"] == "Ankara"
    assert payload["evidence_id"] == item.provenance.evidence_id


def test_canonical_upsert_rejects_cross_workspace_provenance():
    adapter = Neo4jGraphAdapter("workspace-a", RecordingDriver())
    entity = CanonicalEntity.create(
        EntityType.LOCATION,
        "Ankara",
        mentions=(
            EntityMention(
                new_canonical_id(), "Ankara", EntityType.LOCATION, provenance("workspace-b")
            ),
        ),
    )
    try:
        adapter.upsert_canonical_entity(entity, "generation-a")
    except ValueError as exc:
        assert "workspace and generation" in str(exc)
    else:
        raise AssertionError("cross-workspace canonical provenance was accepted")


def test_identity_operation_is_lossless_workspace_scoped_history():
    driver = RecordingDriver()
    adapter = Neo4jGraphAdapter("workspace-a", driver)
    primary_id, duplicate_id = new_canonical_id(), new_canonical_id()
    operation = IdentityOperation(
        new_canonical_id(),
        IdentityDecisionKind.MERGE,
        KnowledgeAuthority.USER_CURATED,
        (primary_id, duplicate_id),
        (primary_id,),
        (provenance().evidence_id,),
        "same person after evidence review",
    )

    adapter.record_identity_operation(operation)

    _, calls = driver.transactions[0]
    query, parameters = calls[0]
    assert "CortexIdentityOperation:CanonicalKnowledge" in query
    assert "IDENTITY_OPERATION_SOURCE" in query
    assert "IDENTITY_OPERATION_RESULT" in query
    assert "DELETE" not in query
    assert parameters["workspace_id"] == "workspace-a"
    assert parameters["source_ids"] == [primary_id, duplicate_id]
    assert parameters["result_ids"] == [primary_id]


def test_manual_merge_transfers_links_and_records_history_without_deletion():
    driver = RecordingDriver()
    primary_id, duplicate_id = new_canonical_id(), new_canonical_id()
    driver.query_results.append(
        [
            {"entity_id": primary_id, "entity_type": "person", "display_name": "Ayşe"},
            {"entity_id": duplicate_id, "entity_type": "person", "display_name": "A. Y."},
        ]
    )
    adapter = Neo4jGraphAdapter("workspace-a", driver)

    operation = adapter.merge_canonical_entities(
        primary_id,
        (duplicate_id,),
        evidence_ids=(provenance().evidence_id,),
        reason="reviewed exact evidence",
    )

    _, calls = driver.transactions[0]
    assert operation.kind is IdentityDecisionKind.MERGE
    assert "HAS_ALIAS" in calls[0][0]
    assert "RESOLVES_TO" in calls[0][0]
    assert all("DELETE" not in query for query, _ in calls)
    assert all(parameters["workspace_id"] == "workspace-a" for _, parameters in calls)


def test_manual_split_requires_a_lossless_mention_partition():
    driver = RecordingDriver()
    source_id = new_canonical_id()
    first_mention, second_mention = new_canonical_id(), new_canonical_id()
    driver.query_results.extend(
        [
            [
                {"entity_type": "person", "mention_id": first_mention},
                {"entity_type": "person", "mention_id": second_mention},
            ],
            [
                {"entity_type": "person", "mention_id": first_mention},
                {"entity_type": "person", "mention_id": second_mention},
            ],
        ]
    )
    adapter = Neo4jGraphAdapter("workspace-a", driver)
    try:
        adapter.split_canonical_entity(
            source_id,
            (("Ayşe", (first_mention,)), ("Aylin", (first_mention,))),
            evidence_ids=(),
            reason="different people",
        )
    except ValueError as exc:
        assert "exactly once" in str(exc)
    else:
        raise AssertionError("overlapping split partition was accepted")

    operation = adapter.split_canonical_entity(
        source_id,
        (("Ayşe", (first_mention,)), ("Aylin", (second_mention,))),
        evidence_ids=(provenance().evidence_id,),
        reason="different people",
    )
    assert operation.kind is IdentityDecisionKind.SPLIT
    assert len(operation.result_entity_ids) == 2
    _, calls = driver.transactions[0]
    assert "old.active = false" in calls[0][0]
    assert all("DELETE" not in query for query, _ in calls)


def test_alias_removal_is_a_user_curated_tombstone_not_a_delete():
    driver = RecordingDriver()
    entity_id, alias_id = new_canonical_id(), new_canonical_id()
    driver.query_results.append([{"alias_id": alias_id, "value": "A. Yılmaz"}])
    adapter = Neo4jGraphAdapter("workspace-a", driver)

    operation = adapter.remove_alias(entity_id, "A. Yılmaz", "incorrect alias")

    assert operation.kind is IdentityDecisionKind.ALIAS_REMOVE
    _, calls = driver.transactions[0]
    alias_query, parameters = calls[0]
    assert parameters["active"] is False
    assert "a.active = $active" in alias_query
    assert all("DELETE" not in query for query, _ in calls)


def test_claim_persistence_keeps_exact_evidence_and_explicit_conflicts():
    driver = RecordingDriver()
    adapter = Neo4jGraphAdapter("workspace-a", driver)
    subject_id = new_canonical_id()
    left = KnowledgeClaim(
        new_canonical_id(),
        subject_id,
        "registered_city",
        "Ankara",
        ClaimStage.SUPPORTED,
        KnowledgeAuthority.VALIDATED,
        "generation-a",
        (provenance(),),
    )
    right = KnowledgeClaim(
        new_canonical_id(),
        subject_id,
        "registered_city",
        "İzmir",
        ClaimStage.SUPPORTED,
        KnowledgeAuthority.VALIDATED,
        "generation-a",
        (provenance(),),
    )

    adapter.upsert_claim(left)
    adapter.upsert_claim(right)
    adapter.link_claim_conflict(link_contradiction(left, right))

    for _, calls in driver.transactions:
        assert "CortexClaim:CanonicalKnowledge" in calls[0][0]
        assert "coalesce(claim.authority_rank, 0) <= $authority_rank" in calls[0][0]
        assert "CortexEvidence:CanonicalKnowledge" in calls[1][0]
        assert calls[1][1]["evidence"][0]["source_text"] == "Ankara"
    conflict_query, conflict_parameters = driver.query_calls[-1]
    assert "CONFLICTS_WITH" in conflict_query
    assert "conflicted = true" in conflict_query
    assert conflict_parameters["workspace_id"] == "workspace-a"
