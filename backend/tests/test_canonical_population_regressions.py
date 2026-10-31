from app.engines.structured.adapter import load_canonical_population
from app.engines.structured.engine import _compare
from app.knowledge.entities import EntityType
from app.knowledge.graph.adapter import (
    CanonicalEntityPropertyQueryView,
    CanonicalEntityQueryView,
    CanonicalEvidenceQueryView,
    CanonicalPopulationQueryView,
    Neo4jGraphAdapter,
)


class RecordingDriver:
    def __init__(self, records=()):
        self.records = records
        self.query = ""

    def execute_query(self, query, **_kwargs):
        self.query = query
        return self.records, None, None


def test_identity_candidates_require_accepted_evidence_not_empty_legacy_entities():
    driver = RecordingDriver()
    graph = Neo4jGraphAdapter("workspace", driver)

    assert graph.identity_candidates("merter", EntityType.PERSON) == ()
    assert "MATCH (m:CortexMention)-[resolution:RESOLVES_TO]->(n)" in driver.query
    assert "OPTIONAL MATCH (m:CortexMention)-[:RESOLVES_TO]->(n)" not in driver.query
    assert "MATCH (m)-[:SUPPORTED_BY]->(e:CortexEvidence" in driver.query
    assert "coalesce(m.lifecycle_status, 'active') = 'active'" in driver.query
    assert "coalesce(resolution.active, true)" in driver.query


def test_surname_property_evidence_is_retained_in_generation_population():
    evidence = CanonicalEvidenceQueryView(
        "evidence", "document", "version", "logical", "chunk", 0, 6, "Merter", 1.0, "generation"
    )
    entity = CanonicalEntityQueryView(
        "person", "person", "Hasan Tahsin Merter", None, (evidence,),
        (CanonicalEntityPropertyQueryView("property", "surname", "MERTER", "string", evidence),),
    )

    class Reader:
        workspace_id = "workspace"

        def query_canonical_population(self, generation, resource, *, safe_limit=500):
            return CanonicalPopulationQueryView(
                "workspace", generation, resource, (entity,), 1, True
            )

    population = load_canonical_population(Reader(), "generation", "person")
    assert population.records[0].values["surname"] == "MERTER"
    assert {item.evidence_id for item in population.records[0].evidence} == {"evidence"}


def test_surname_filter_normalizes_case_without_grouping_by_display_name():
    assert _compare("MERTER", "eq", "Merter", normalized_string=True)
    assert _compare("Merter", "eq", "MERTER", normalized_string=True)
    assert not _compare("Mert", "eq", "Merter", normalized_string=True)


def test_unresolved_population_member_is_not_promoted_to_structured_record():
    class Reader:
        workspace_id = "workspace"

        def query_canonical_population(self, generation, resource, *, safe_limit=500):
            entity = CanonicalEntityQueryView("person", "person", "Merter", None, ())
            return CanonicalPopulationQueryView(
                "workspace", generation, resource, (entity,), 1, True
            )

    population = load_canonical_population(Reader(), "generation", "person")
    assert population.records == ()
    assert not population.safely_enumerable
