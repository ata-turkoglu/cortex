from dataclasses import dataclass, field

from app.knowledge.construction_projection import (
    ConstructedKnowledge,
    construct_from_bundle,
    promote_constructed_claims,
    promote_constructed_knowledge,
)
from app.knowledge.extraction import (
    ExtractedClaim,
    ExtractedMention,
    ExtractedRelation,
    ExtractedSpan,
    ExtractedTemporal,
    ExtractionMetadata,
    KnowledgeExtractionBundle,
)
from app.knowledge.pipeline import CorpusSnapshot, SourceChunk


def test_constructs_typed_evidence_backed_proposals():
    text = "Ayse moved to Ankara in 2024"
    snapshot = CorpusSnapshot(
        "workspace",
        "fingerprint",
        (SourceChunk("chunk", "doc", "version", "logical", 0, text, "hash"),),
    )
    def span(value):
        start = text.index(value)
        return ExtractedSpan("chunk", start, start + len(value), value, 0.9)
    bundle = KnowledgeExtractionBundle(
        ExtractionMetadata("run", "openai", "model", "prompt", "schema"),
        mentions=(
            ExtractedMention("person", "person", span("Ayse")),
            ExtractedMention("place", "location", span("Ankara")),
        ),
        relations=(ExtractedRelation("moved_to", "person", "place", span("moved to Ankara")),),
        temporals=(
            ExtractedTemporal(
                "date", "2024", "2024", "2024", "event_time", "year", False, span("2024")
            ),
        ),
        claims=(ExtractedClaim("person", "moved_to", "Ankara", span("moved to Ankara")),),
    )
    result = construct_from_bundle(
        bundle,
        snapshot,
        "generation",
        {
            "person": "00000000-0000-0000-0000-000000000001",
            "place": "00000000-0000-0000-0000-000000000002",
        },
    )
    assert len(result.relations) == len(result.temporals) == len(result.claims) == 1
    assert result.claims[0].evidence[0].source_text == "moved to Ankara"


@dataclass
class FakeClaimStore:
    workspace_id: str = "workspace"
    claims: list = field(default_factory=list)

    def upsert_claim(self, claim):
        self.claims.append(claim)


def test_promotes_supported_claims_through_canonical_store():
    claim = object()
    constructed = ConstructedKnowledge((), (), (), (claim,))
    store = FakeClaimStore()
    assert promote_constructed_claims(store, CorpusSnapshot("workspace", "f", ()), constructed) == 1
    assert store.claims == [claim]


@dataclass
class FakeKnowledgeStore(FakeClaimStore):
    relations: list = field(default_factory=list)
    events: list = field(default_factory=list)
    temporals: list = field(default_factory=list)

    def upsert_relation(self, relation):
        self.relations.append(relation)

    def upsert_event(self, event):
        self.events.append(event)

    def upsert_temporal(self, temporal):
        self.temporals.append(temporal)


def test_promotes_all_constructed_types_through_one_store_boundary():
    relation, event, temporal, claim = object(), object(), object(), object()
    constructed = ConstructedKnowledge((relation,), (event,), (temporal,), (claim,))
    store = FakeKnowledgeStore()
    result = promote_constructed_knowledge(
        store, CorpusSnapshot("workspace", "f", ()), constructed
    )
    assert result == {"relations": 1, "events": 1, "temporals": 1, "claims": 1}
    assert store.relations == [relation]
    assert store.events == [event]
    assert store.temporals == [temporal]
    assert store.claims == [claim]
