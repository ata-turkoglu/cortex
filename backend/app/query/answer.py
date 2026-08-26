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
            content = self._unsupported(package)
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
        return "I need clarification before answering because multiple interpretations remain" + (
            f": {reasons}." if reasons else "."
        )

    @staticmethod
    def _unsupported(package: ReasoningPackage) -> str:
        if any(issue.startswith("capability_unavailable:") for issue in package.issues):
            return (
                "This request requires a knowledge capability that is not ready for this "
                "workspace. I can still help with grounded document-retrieval questions."
            )
        return "I could not find enough validated evidence to answer that safely."

    @staticmethod
    def _grounded(package: ReasoningPackage) -> str:
        values: list[str] = []
        # An exhaustive structured result is already a bounded, deterministic answer
        # set selected by the physical plan.  Truncating it here would silently turn
        # "list every person" requests into a partial answer after reconciliation.
        if package.state == "corpus_complete" and package.structured_rows:
            ranked_people = [
                item for item in package.structured_rows
                if item.values.get("entity_type") == "person"
                and item.values.get("display_name")
                and "property_count" in item.values
            ]
            if ranked_people:
                lines = [
                    f"{index}. {item.values['display_name']} — "
                    f"{int(item.values['property_count'])} property record"
                    f"{'s' if int(item.values['property_count']) != 1 else ''}"
                    for index, item in enumerate(ranked_people, start=1)
                ]
                return (
                    "People found in the active documents, ranked by distinct property records:\n"
                    + "\n".join(lines)
                )
            values.extend(
                ", ".join(
                    f"{key}: {value}"
                    for key, value in item.values.items()
                    if value is not None
                    and key not in {"entity_id", "entity_type", "workspace_id", "generation_id"}
                )
                for item in package.structured_rows
            )
            return "The complete workspace result is: " + "; ".join(values) + "."
        for event in package.events:
            if len(values) == 3:
                break
            participants = ", ".join(event.participant_canonical_ids)
            values.append(
                f"{event.event_date}: {event.event_name} ({event.event_type})"
                + (f"; participants: {participants}" if participants else "")
            )
        for item in (*package.structured_rows, *package.entities, *package.claims):
            if len(values) == 3:
                break
            rendered = ", ".join(
                f"{key}: {value}"
                for key, value in item.values.items()
                if value is not None
                and key not in {"entity_id", "entity_type", "workspace_id", "generation_id"}
            )
            if rendered:
                values.append(rendered)
        for finding in package.graphrag_findings:
            if len(values) == 3:
                break
            values.append(f"GraphRAG {finding.mode} finding: {finding.text}")
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
