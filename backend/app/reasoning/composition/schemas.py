"""Grounded outline, section, and final-artifact contracts."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

COMPOSITION_SCHEMA_VERSION = "1.0"


class OutlineSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    section_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$", max_length=128)
    title: str = Field(min_length=1, max_length=500)
    objective: str = Field(min_length=1, max_length=2_000)
    order: int = Field(ge=1, le=10_000)


class GroundedSentence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sentence_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=20_000)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=10_000)


class GroundedParagraph(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    paragraph_id: str = Field(min_length=1, max_length=128)
    sentences: tuple[GroundedSentence, ...] = Field(min_length=1, max_length=1_000)


class DraftSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    section_id: str
    state: Literal["pending", "drafting", "drafted", "validated", "failed"] = "pending"
    paragraphs: tuple[GroundedParagraph, ...] = Field(default=(), max_length=10_000)
    consistency_issues: tuple[str, ...] = Field(default=(), max_length=1_000)


class FinalArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str
    markdown: str = Field(min_length=1)
    sentence_evidence: dict[str, tuple[str, ...]]


class CompositionCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = COMPOSITION_SCHEMA_VERSION
    run_id: str
    research_run_id: str
    workspace_id: str
    title: str = Field(min_length=1, max_length=500)
    state: Literal[
        "created", "outlining", "drafting", "validating", "ready", "failed"
    ] = "created"
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=100_000)
    outline: tuple[OutlineSection, ...] = Field(default=(), max_length=10_000)
    sections: tuple[DraftSection, ...] = Field(default=(), max_length=10_000)
    validation_issues: tuple[str, ...] = Field(default=(), max_length=10_000)
    final_artifact: FinalArtifact | None = None

    @model_validator(mode="after")
    def grounded_and_consistent(self):
        allowed = set(self.evidence_ids)
        outline_ids = [item.section_id for item in self.outline]
        if len(outline_ids) != len(set(outline_ids)):
            raise ValueError("composition outline section IDs must be unique")
        if self.outline and sorted(item.order for item in self.outline) != list(
            range(1, len(self.outline) + 1)
        ):
            raise ValueError("composition outline order must be contiguous")
        section_ids = [item.section_id for item in self.sections]
        if len(section_ids) != len(set(section_ids)) or set(section_ids) - set(outline_ids):
            raise ValueError("draft sections must map uniquely to the outline")
        sentences = [
            sentence for section in self.sections for paragraph in section.paragraphs
            for sentence in paragraph.sentences
        ]
        if any(not set(sentence.evidence_ids) <= allowed for sentence in sentences):
            raise ValueError("composition sentences cannot cite uncollected evidence")
        if self.state == "ready":
            if (
                not self.final_artifact or self.validation_issues
                or set(section_ids) != set(outline_ids)
                or any(section.state != "validated" for section in self.sections)
            ):
                raise ValueError("ready composition requires every section to be validated")
            expected = {
                sentence.sentence_id: sentence.evidence_ids for sentence in sentences
            }
            if self.final_artifact.sentence_evidence != expected:
                raise ValueError("final artifact must preserve every sentence evidence mapping")
        return self


class SectionComposer(Protocol):
    def draft(
        self, title: str, section: OutlineSection, evidence_ids: tuple[str, ...]
    ) -> DraftSection: ...
