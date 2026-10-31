"""Regression coverage for durable canonical identity auditability."""

from app.knowledge.entities import EntityType
from app.knowledge.graph import Neo4jGraphAdapter


class _Result:
    def consume(self):
        return None


class _Transaction:
    def __init__(self):
        self.calls = []

    def run(self, query, **parameters):
        self.calls.append((query, parameters))
        return _Result()


class _Session:
    def __init__(self, driver, database):
        self.driver = driver
        self.database = database

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute_write(self, callback, *args, **kwargs):
        transaction = _Transaction()
        callback(transaction, *args, **kwargs)
        self.driver.transactions.append(transaction.calls)


class _Driver:
    def __init__(self):
        self.transactions = []
        self.queries = []

    def session(self, *, database):
        return _Session(self, database)

    def execute_query(self, query, **parameters):
        self.queries.append((query, parameters))
        return ([], None, [])


def test_generation_cleanup_retires_unaccepted_identities_without_deleting_history():
    driver = _Driver()
    Neo4jGraphAdapter("workspace-a", driver).clear_generation_materialization("generation-a")

    queries = [query for query, _ in driver.transactions[0]]
    canonical_cleanup = [query for query in queries if "authority: 'extracted'" in query]

    assert len(canonical_cleanup) == 1
    assert "SET n.status = 'retired'" in canonical_cleanup[0]
    assert "DETACH DELETE n" not in canonical_cleanup[0]
    assert "m.decision IN ['auto_link', 'new_canonical', 'manual_link']" in canonical_cleanup[0]


def test_generation_cleanup_retires_mentions_properties_and_relations_without_delete():
    driver = _Driver()
    Neo4jGraphAdapter("workspace-a", driver).clear_generation_materialization("generation-a")

    queries = [query for query, _ in driver.transactions[0]]
    relation, property_, mention = queries[:3], queries[2], queries[3]
    assert "SET r.active = false, r.lifecycle_status = 'retired'" in relation[0]
    assert "DETACH DELETE" not in property_
    assert "p.lifecycle_status = 'retired'" in property_
    assert "DETACH DELETE" not in mention
    assert "m.lifecycle_status = 'retired'" in mention


def test_active_candidate_lookup_excludes_retired_and_superseded_identities():
    driver = _Driver()
    Neo4jGraphAdapter("workspace-a", driver).identity_candidates("ayse yilmaz", EntityType.PERSON)

    query, _ = driver.queries[0]
    assert "status: 'active'" in query
    assert "status: 'retired'" not in query
    assert "status: 'superseded'" not in query
    assert "m.lifecycle_status" in query
    assert "resolution.active" in query


def test_historical_evidence_read_keeps_predecessor_mentions_auditable():
    driver = _Driver()
    adapter = Neo4jGraphAdapter("workspace-a", driver)

    # UUID validation occurs before the query; this only verifies the audit predicate.
    adapter.entity_evidence("11111111-1111-1111-1111-111111111111")

    query, _ = driver.queries[0]
    assert "RESOLVES_TO" in query
    assert "coalesce(resolution.active, true)" not in query


def test_audit_lookup_is_status_independent_and_artifact_references_fail_closed():
    driver = _Driver()
    adapter = Neo4jGraphAdapter("workspace-a", driver)
    entity_id = "11111111-1111-1111-1111-111111111111"

    assert adapter.audit_canonical_identity(entity_id) is None
    query, _ = driver.queries[0]
    assert "external_id: $entity_id" in query
    assert "status: 'active'" not in query
    try:
        adapter.validate_identity_artifact_references((entity_id,))
    except ValueError as exc:
        assert "unrecoverable canonical IDs" in str(exc)
    else:
        raise AssertionError("unrecoverable artifact reference was accepted")
