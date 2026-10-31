from dataclasses import dataclass, field

from app.knowledge.extraction import (
    ExtractedMention,
    ExtractedSpan,
    ExtractionMetadata,
    KnowledgeExtractionBundle,
)
from app.knowledge.pipeline import CorpusSnapshot, SourceChunk
from app.knowledge.promotion import promote_extracted_entities


@dataclass
class FakeStore:
    workspace_id: str = "workspace-a"
    entities: list = field(default_factory=list)

    def upsert_canonical_entity(self, entity, generation):
        self.entities.append((entity, generation))


def test_promotes_only_exact_evidence_backed_extracted_entity_proposals():
    snapshot = CorpusSnapshot(
        "workspace-a",
        "fingerprint",
        (SourceChunk("chunk", "doc", "version", "logical", 0, "Ayse", "hash"),),
    )
    bundle = KnowledgeExtractionBundle(
        ExtractionMetadata("run", "openai", "model", "prompt", "schema"),
        mentions=(ExtractedMention("local", "person", ExtractedSpan("chunk", 0, 4, "Ayse", 0.9)),),
    )
    store = FakeStore()
    summary = promote_extracted_entities(store, snapshot, "generation", (bundle,))
    assert summary.entity_count == summary.mention_count == 1
    entity, generation = store.entities[0]
    assert generation == "generation"
    assert entity.mentions[0].provenance.source_text == "Ayse"
    assert entity.authority.name == "EXTRACTED"
