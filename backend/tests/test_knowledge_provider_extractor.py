import asyncio
from dataclasses import dataclass

import pytest

from app.knowledge.pipeline import CorpusSnapshot, SourceChunk
from app.knowledge.provider_extractor import OpenAIKnowledgeExtractor
from app.providers.base import GeneratedText


@dataclass
class FakeProvider:
    async def generate(self, model, instructions, input_text):
        assert model == "test-model"
        assert "Never infer" in instructions
        return GeneratedText(
            '{"mentions":[{"id":"person","entity_type":"person","chunk_id":"chunk-a","start_offset":0,"end_offset":4,"source_text":"Ayse","confidence":0.9}]}',
            request_id="provider-run",
        )


def test_provider_extraction_validates_exact_spans_before_returning_results():
    snapshot = CorpusSnapshot(
        "workspace-a",
        "fingerprint-a",
        (SourceChunk("chunk-a", "doc-a", "version-a", "logical-a", 0, "Ayse", "hash-a"),),
    )
    result = OpenAIKnowledgeExtractor("test-model", FakeProvider()).extract(
        snapshot, "generation-a"
    )
    assert result.evidence_count == 1
    assert result.bundles[0].metadata.extraction_run_id == "provider-run"


@dataclass
class HangingProvider:
    async def generate(self, model, instructions, input_text):
        await asyncio.sleep(60)


def test_provider_extraction_times_out_a_stalled_provider_request():
    snapshot = CorpusSnapshot(
        "workspace-a",
        "fingerprint-a",
        (SourceChunk("chunk-a", "doc-a", "version-a", "logical-a", 0, "Ayse", "hash-a"),),
    )
    extractor = OpenAIKnowledgeExtractor(
        "test-model",
        HangingProvider(),
        request_timeout_seconds=0.01,
        retry_delay_seconds=0,
    )

    with pytest.raises(RuntimeError, match="timed out after 0.01s for chunk chunk-a"):
        extractor.extract(snapshot, "generation-a")
