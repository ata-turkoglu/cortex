import asyncio
import json

import pytest

from app.providers.base import GeneratedText
from app.query.answer import AnswerEngine
from app.query.answer_synthesis import (
    AnswerSynthesizer,
    SynthesisValidationError,
    apply_synthesis,
    is_eligible,
    validate_sentences,
)
from app.query.orchestration import (
    CompletenessReport,
    GroundedItem,
    MaterializedCitation,
    ReasoningPackage,
)

EVIDENCE = {
    "e1": "Ali Merter 1952 yılında Moda 303 ada 16 parselde tapu aldı.",
    "e2": "Ayşe Merter arşivde tanık olarak geçer.",
}


def _citation(evidence_id, rank):
    return MaterializedCitation(
        citation_id=f"c-{evidence_id}",
        evidence_id=evidence_id,
        document_id=f"doc-{evidence_id}",
        document_version_id=f"ver-{evidence_id}",
        logical_document_id=f"log-{evidence_id}",
        chunk_id=f"chunk-{evidence_id}",
        start_offset=0,
        end_offset=len(EVIDENCE[evidence_id]),
        source_text=EVIDENCE[evidence_id],
        label=f"Belge {rank}",
        rank=rank,
        score=1.0,
        supporting_step_ids=("retrieve",),
    )


def _package(**changes):
    values = {
        "workspace_id": "workspace",
        "generation_id": "generation",
        "state": "grounded",
        "structured_rows": (
            GroundedItem(item_id="r1", evidence_ids=("e1",), values={"fusion_rank": 1}),
        ),
        "citations": (_citation("e1", 1), _citation("e2", 2)),
        "completeness": CompletenessReport(coverage="grounded", state="unknown"),
        "confidence": 0.9,
    }
    values.update(changes)
    return ReasoningPackage(**values)


def _payload(*sentences, insufficient=False):
    return {
        "insufficient": insufficient,
        "sentences": [{"text": text, "evidence_ids": list(ids)} for text, ids in sentences],
    }


def test_valid_sentences_keep_their_evidence():
    sentences = validate_sentences(
        _payload(("Ali Merter 1952'de 303 ada 16 parselde tapu aldı.", ("e1",))),
        EVIDENCE,
        "balanced",
    )
    assert sentences == (("Ali Merter 1952'de 303 ada 16 parselde tapu aldı.", ("e1",)),)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (_payload(("Ali Merter tapu aldı.", ("e9",))), "unknown evidence"),
        (_payload(("Ali Merter tapu aldı.", ())), "no text or evidence"),
        (_payload(("Ali Merter 1953'te tapu aldı.", ("e1",))), "absent from its evidence"),
        (_payload(("Ali Merter 2 parsel aldı.", ("e1",))), "absent from its evidence"),
        (_payload(("Ayşe Merter 16 parselin sahibidir.", ("e2",))), "absent from its evidence"),
        (_payload(("Ayşe Merter bir parselin sahibidir.", ("e2",))), "without cadastral evidence"),
        (_payload(("Kaynak e1 bunu söyler.", ("e1",))), "internal metadata"),
        (_payload(insufficient=True), "insufficient"),
        (_payload(*[("Ali Merter tapu aldı.", ("e1",))] * 3), "more than 2"),
    ],
)
def test_untraceable_sentences_are_rejected(payload, message):
    style = "concise" if "more than" in message else "balanced"
    with pytest.raises(SynthesisValidationError, match=message):
        validate_sentences(payload, EVIDENCE, style)


class _Provider:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.inputs = []

    async def generate_structured(self, model, instructions, input_text, **schema):
        self.inputs.append(json.loads(input_text))
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return GeneratedText(json.dumps(output), input_tokens=10, output_tokens=5)


def _synthesizer(provider, limit=10):
    return AnswerSynthesizer(
        provider, provider_name="openai", model="m", style="balanced", evidence_limit=limit
    )


def test_synthesis_repairs_once_then_falls_back_without_changing_the_answer():
    repaired = _Provider(
        _payload(("Ali Merter 1999'da tapu aldı.", ("e1",))),
        _payload(("Ayşe Merter tanıktır.", ("e2",)), ("Ali Merter 1952'de tapu aldı.", ("e1",))),
    )
    outcome = asyncio.run(_synthesizer(repaired).synthesize("Kim?", _package()))
    assert outcome.status == "synthesized" and len(outcome.attempts) == 2

    failing = _Provider(_payload(insufficient=True), _payload(insufficient=True))
    outcome = asyncio.run(_synthesizer(failing).synthesize("Kim?", _package()))
    assert (outcome.status, outcome.reason, len(outcome.attempts)) == (
        "fallback",
        "validation_failed",
        2,
    )

    outage = _Provider(RuntimeError("down"))
    outcome = asyncio.run(_synthesizer(outage).synthesize("Kim?", _package()))
    assert (outcome.status, outcome.reason) == ("fallback", "provider_error")


def test_only_the_configured_number_of_evidence_items_is_sent():
    provider = _Provider(_payload(("Ali Merter tapu aldı.", ("e1",))))
    asyncio.run(_synthesizer(provider, limit=1).synthesize("Kim?", _package()))
    assert [item["evidence_id"] for item in provider.inputs[0]["evidence"]] == ["e1"]


def test_synthesized_citations_are_exactly_the_cited_evidence_in_cited_order():
    package = _package()
    provider = _Provider(
        _payload(("Ayşe Merter tanıktır.", ("e2",)), ("Ali Merter 1952'de tapu aldı.", ("e1",)))
    )
    outcome = asyncio.run(_synthesizer(provider).synthesize("Kim?", package))
    draft = apply_synthesis(AnswerEngine().render(package), package, outcome)

    assert draft.content == "Ayşe Merter tanıktır. [1] Ali Merter 1952'de tapu aldı. [2]"
    assert [item["chunk_id"] for item in draft.citations] == ["chunk-e2", "chunk-e1"]
    assert draft.metadata["answer_synthesis"] == "synthesized"
    assert draft.metadata["inference"] is True
    assert draft.state == "grounded"


def test_structured_partial_and_unsupported_results_are_never_synthesized():
    assert is_eligible(_package()) is True
    assert is_eligible(_package(state="partial")) is False
    assert is_eligible(_package(state="unsupported", citations=())) is False
    assert (
        is_eligible(
            _package(
                structured_rows=(
                    GroundedItem(item_id="p", evidence_ids=("e1",), values={"display_name": "Ali"}),
                )
            )
        )
        is False
    )


def test_ordinary_words_are_not_mistaken_for_parcel_terms():
    sentence = "Ayşe Merter Adana'da bir adamla görüştü."
    assert validate_sentences(_payload((sentence, ("e2",))), EVIDENCE, "balanced")
