"""The sole V2 boundary permitted to render user-facing answer prose.

This module deliberately accepts a reconciled ReasoningPackage rather than
engine output. Persistence stays with the runtime adapter so rendering is pure,
testable, and cannot hold a SQLite transaction across provider work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .orchestration import ReasoningPackage


@dataclass(frozen=True)
class AnswerDraft:
    """A grounded, render-ready V2 response with only validated citations."""

    content: str
    state: Literal["grounded", "corpus_complete", "partial", "unsupported", "ambiguous"]
    citations: tuple[dict[str, str], ...]
    metadata: dict[str, object]


class AnswerEngine:
    """Render a conservative answer from Result & Evidence, never raw engine output."""

    def render(self, package: ReasoningPackage) -> AnswerDraft:
        citations = tuple(
            {
                "document_id": citation.document_id,
                "document_version_id": citation.document_version_id,
                "chunk_id": citation.chunk_id,
                "label": citation.label,
            }
            for citation in package.citations
        )
        if package.state == "ambiguous":
            content = self._clarification(package)
        elif package.state == "unsupported":
            content = "I could not find enough validated evidence to answer that safely."
        else:
            content = self._grounded(package)
        return AnswerDraft(
            content=content,
            state=package.state,
            citations=citations,
            metadata={
                "answer_engine": "query_v2",
                "answer_state": package.state,
                "generation_id": package.generation_id,
                "confidence": package.confidence,
                "coverage": package.completeness.model_dump(mode="json"),
                "issues": list(package.issues),
                "ambiguities": [item.model_dump(mode="json") for item in package.ambiguities],
            },
        )

    @staticmethod
    def _clarification(package: ReasoningPackage) -> str:
        reasons = "; ".join(item.reason for item in package.ambiguities[:3])
        return (
            "I need clarification before answering because multiple interpretations remain"
            + (f": {reasons}." if reasons else ".")
        )

    @staticmethod
    def _grounded(package: ReasoningPackage) -> str:
        values: list[str] = []
        for item in (*package.structured_rows, *package.entities, *package.claims):
            if len(values) == 3:
                break
            rendered = ", ".join(
                f"{key}: {value}" for key, value in item.values.items() if value is not None
            )
            if rendered:
                values.append(rendered)
        if package.aggregates:
            remaining = max(0, 3 - len(values))
            values.extend(
                f"{item.function}: {item.value}" for item in package.aggregates[:remaining]
            )
        if not values:
            return "Validated evidence was found, but it does not support a concise direct answer."
        qualifier = (
            "The complete workspace result is: "
            if package.state == "corpus_complete"
            else "Based on the validated evidence: "
        )
        suffix = " Some requested coverage is incomplete." if package.state == "partial" else ""
        return qualifier + "; ".join(values) + "." + suffix
