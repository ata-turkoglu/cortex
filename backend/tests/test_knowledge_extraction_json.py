import pytest

from app.knowledge.extraction import ExtractionMetadata
from app.knowledge.extraction_json import decode_extraction_json


def metadata():
    return ExtractionMetadata("run", "openai", "model", "prompt", "schema")


def test_decodes_provider_schema_before_exact_source_validation():
    bundle = decode_extraction_json(
        '{"mentions":[{"id":"person","entity_type":"person","chunk_id":"chunk","start_offset":0,"end_offset":4,"source_text":"Ayse","confidence":0.9}],"events":[{"id":"move","event_type":"move","participants":[{"mention_id":"person"}],"chunk_id":"chunk","start_offset":0,"end_offset":4,"source_text":"Ayse","confidence":0.9}]}',
        metadata(),
    )
    assert bundle.mentions[0].local_id == "person"
    assert bundle.events[0].participant_mention_ids == ("person",)


def test_rejects_non_json_or_invalid_schema_types():
    with pytest.raises(ValueError, match="valid JSON"):
        decode_extraction_json("not json", metadata())
    with pytest.raises(ValueError, match="confidence"):
        decode_extraction_json(
            '{"mentions":[{"id":"person","entity_type":"person","chunk_id":"chunk","start_offset":0,"end_offset":4,"source_text":"Ayse","confidence":"high"}]}',
            metadata(),
        )
