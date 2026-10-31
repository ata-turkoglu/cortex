"""The sole V2 boundary permitted to render user-facing answer prose.

This module deliberately accepts a reconciled ReasoningPackage rather than
engine output. Persistence stays with the runtime adapter so rendering is pure,
testable, and cannot hold a SQLite transaction across provider work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .orchestration import CompletenessReport, ReasoningPackage
from .presentation import (
    build_canonical_person_presentations,
    group_canonical_person_presentations,
)


@dataclass(frozen=True)
class AnswerDraft:
    """A grounded, render-ready V2 response with only validated citations."""

    content: str
    state: Literal["grounded", "corpus_complete", "partial", "unsupported", "ambiguous"]
    citations: tuple[dict[str, str], ...]
    metadata: dict[str, object]


class AnswerEngine:
    """Render a conservative answer from Result & Evidence, never raw engine output."""

    _MAX_VISIBLE_CITATIONS = 3
    _INTERNAL_VALUE_KEYS = frozenset(
        {
            "evidence",
            "fusion_rank",
            "dense_rank",
            "sparse_rank",
            "rrf_score",
            "retrieval_score",
            "chunk_id",
            "document_version_id",
            "knowledge_generation_id",
        }
    )

    def render(self, package: ReasoningPackage) -> AnswerDraft:
        content, evidence_ids = self._content_and_evidence(package)
        presentations = build_canonical_person_presentations(package.structured_rows)
        citations = tuple(
            {
                "document_id": citation.document_id,
                "document_version_id": citation.document_version_id,
                "chunk_id": citation.chunk_id,
                "label": citation.label,
            }
            for citation in package.citations
            if citation.evidence_id in evidence_ids
        )
        return AnswerDraft(
            content=content,
            state=package.state,
            citations=citations,
            metadata={
                "answer_engine": "query_v2",
                "answer_state": package.state,
                "reason_code": package.failure_reason,
                "generation_id": package.generation_id,
                "confidence": package.confidence,
                "coverage": package.completeness.model_dump(mode="json"),
                "issues": list(package.issues),
                "ambiguities": [item.model_dump(mode="json") for item in package.ambiguities],
                "canonical_person_presentations": [
                    {
                        "canonical_entity_id": item.canonical_entity_id,
                        "original_preferred_name": item.original_preferred_name,
                        "display_label": item.display_label,
                        "same_name_candidate_count": item.same_name_candidate_count,
                    }
                    for item in presentations.values()
                ],
            },
        )

    def _content_and_evidence(self, package: ReasoningPackage) -> tuple[str, frozenset[str]]:
        if package.state == "ambiguous":
            return self._clarification(package), frozenset()
        if package.state == "unsupported":
            return self._unsupported(package), frozenset()
        content, evidence_ids = self._grounded(package)
        return content, frozenset(evidence_ids)

    @staticmethod
    def _clarification(package: ReasoningPackage) -> str:
        if package.failure_reason == "identity_ambiguous":
            return (
                "Bu ad birden fazla kişi kaydıyla eşleşebildiği için yanlış kişiye veri "
                "atfetmemek adına kesin sonuç veremiyorum. Hangi kişiyi kastettiğinizi "
                "belirtirseniz sorguyu yeniden çalıştırabilirim."
            )
        return (
            "Soruyu güvenilir biçimde tek bir anlama indirgeyemedim. "
            "Biraz daha açık belirtebilirsiniz."
        )

    @staticmethod
    def _unsupported(package: ReasoningPackage) -> str:
        reason = package.failure_reason
        if reason == "identity_unresolved":
            return (
                "Bu kişi için güvenilir tek bir kanonik kimlik kaydı çözümlenemediği için "
                "kesin sonuç veremiyorum."
            )
        if reason == "identity_ambiguous":
            return (
                "Bu ad birden fazla kişi kaydıyla eşleşebildiği için yanlış kişiye veri "
                "atfetmemek adına kesin sonuç veremiyorum."
            )
        if reason == "unsupported_operation" or any(
            issue.startswith("capability_unavailable:") for issue in package.issues
        ):
            return (
                "Bu sorgu türü mevcut veri ve sorgu yetenekleriyle "
                "güvenli biçimde çalıştırılamıyor."
            )
        if reason == "query_not_understood":
            return (
                "Soruyu güvenilir biçimde yapılandıramadım. Kişi, ilişki veya "
                "ölçütü biraz daha açık belirtebilirsiniz."
            )
        return "Bu soruyu güvenilir biçimde yanıtlamak için yeterli doğrulanmış kanıt bulunamadı."

    @staticmethod
    def failure_content(reason: Literal["query_not_understood", "unsupported_operation"]) -> str:
        """Use the same safe, user-facing renderer for pre-package failures."""
        package = ReasoningPackage(
            workspace_id="failure",
            state="unsupported",
            completeness=CompletenessReport(coverage="grounded", state="unknown"),
            confidence=0.0,
            failure_reason=reason,
        )
        return AnswerEngine._unsupported(package)

    @staticmethod
    def _grounded(package: ReasoningPackage) -> tuple[str, tuple[str, ...]]:
        query_completeness = package.completeness.query
        if query_completeness and query_completeness.status == "PARTIAL":
            return (
                AnswerEngine._partial_structured(package),
                AnswerEngine._visible_evidence_ids(package),
            )
        if AnswerEngine._is_retrieval_only(package):
            return AnswerEngine._retrieval_summary(package)
        values: list[str] = []
        # An exhaustive structured result is already a bounded, deterministic answer
        # set selected by the physical plan.  Truncating it here would silently turn
        # "list every person" requests into a partial answer after reconciliation.
        if package.state == "corpus_complete" and package.structured_rows:
            presentations = build_canonical_person_presentations(package.structured_rows)
            ranked_people = [
                item
                for item in package.structured_rows
                if item.values.get("entity_type") == "person"
                and item.values.get("display_name")
                and "property_count" in item.values
            ]
            if ranked_people:
                lines = [
                    f"{index}. {AnswerEngine._person_label(item, presentations)} — "
                    f"{int(item.values['property_count'])} property record"
                    f"{'s' if int(item.values['property_count']) != 1 else ''}"
                    for index, item in enumerate(ranked_people, start=1)
                ]
                return (
                    "Etkin belgelerdeki farklı taşınmaz kayıtlarına göre sıralama:\n"
                    + "\n".join(lines)
                ), AnswerEngine._visible_evidence_ids(package)
            people = AnswerEngine._person_rows(package)
            if people and len(people) == len(package.structured_rows):
                groups = group_canonical_person_presentations(people)
                return (
                    AnswerEngine._person_inventory_heading(len(people), len(groups))
                    + "\n\n"
                    + "\n".join(AnswerEngine._person_group_line(group) for group in groups),
                    AnswerEngine._visible_evidence_ids(package),
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
            return (
                "Etkin çalışma alanındaki tam sonuç: " + "; ".join(values) + ".",
                AnswerEngine._visible_evidence_ids(package),
            )
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
                and key
                not in {"entity_id", "entity_type", "workspace_id", "generation_id"}
                | AnswerEngine._INTERNAL_VALUE_KEYS
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
            return (
                "Doğrulanmış kaynaklar bulundu, ancak bunlardan kısa ve doğrudan bir yanıt "
                "güvenli biçimde oluşturulamadı.",
                AnswerEngine._visible_evidence_ids(package),
            )
        qualifier = (
            "Etkin çalışma alanındaki tam sonuç: "
            if package.state == "corpus_complete"
            else "Doğrulanmış kanıtlara göre: "
        )
        suffix = " İstenen kapsamın bir bölümü eksik." if package.state == "partial" else ""
        return (
            qualifier + "; ".join(values) + "." + suffix,
            AnswerEngine._visible_evidence_ids(package),
        )

    @staticmethod
    def _is_retrieval_only(package: ReasoningPackage) -> bool:
        return bool(package.citations) and bool(package.structured_rows) and not any(
            set(item.values) - AnswerEngine._INTERNAL_VALUE_KEYS for item in package.structured_rows
        ) and not (
            package.entities
            or package.events
            or package.aggregates
            or package.graphrag_findings
            or package.claims
        )

    @staticmethod
    def _retrieval_summary(package: ReasoningPackage) -> tuple[str, tuple[str, ...]]:
        citations = package.citations[: AnswerEngine._MAX_VISIBLE_CITATIONS]
        snippets = [AnswerEngine._safe_excerpt(item.source_text) for item in citations]
        snippets = [item for item in snippets if item]
        if not snippets:
            return (
                "Bu sorgu için doğrulanmış kaynaklar bulundu; ayrıntıları kaynak "
                "kartlarından inceleyebilirsiniz.",
                tuple(item.evidence_id for item in citations),
            )
        return (
            "Doğrulanmış arşiv kaynaklarında soruyla ilişkili bilgiler bulundu:\n"
            + "\n".join(f"- {snippet}" for snippet in snippets),
            tuple(item.evidence_id for item in citations),
        )

    @staticmethod
    def _safe_excerpt(source_text: str) -> str | None:
        """Return a short source-derived sentence, never serialized runtime metadata."""
        normalized = " ".join(source_text.split())
        if not normalized or any(
            token in normalized.lower() for token in AnswerEngine._INTERNAL_VALUE_KEYS
        ):
            return None
        for boundary in (". ", "! ", "? "):
            if boundary in normalized:
                normalized = normalized.split(boundary, 1)[0] + boundary.strip()
                break
        return normalized[:280].rstrip(" ,;:") + ("…" if len(normalized) > 280 else "")

    @staticmethod
    def _visible_evidence_ids(package: ReasoningPackage) -> tuple[str, ...]:
        return tuple(
            item.evidence_id for item in package.citations[: AnswerEngine._MAX_VISIBLE_CITATIONS]
        )

    @staticmethod
    def _partial_structured(package: ReasoningPackage) -> str:
        """State known facts plainly without converting a partial result to exactness."""
        query = package.completeness.query
        assert query is not None
        if package.aggregates and isinstance(package.aggregates[0].value, int):
            content = (
                f"Kanonik kayıtlarda kesin olarak {package.aggregates[0].value} kişi bulunuyor."
            )
        elif package.structured_rows:
            presentations = build_canonical_person_presentations(package.structured_rows)
            ranked = [
                item
                for item in package.structured_rows
                if item.values.get("display_name") and "property_count" in item.values
            ]
            if ranked:
                content = "Bilinen kanonik kişiler için sıralama:\n" + "\n".join(
                    f"{index}. {AnswerEngine._person_label(item, presentations)} — "
                    f"{int(item.values['property_count'])} taşınmaz kaydı"
                    for index, item in enumerate(ranked, start=1)
                )
            else:
                people = AnswerEngine._person_rows(package)
                if people:
                    groups = group_canonical_person_presentations(people)
                    content = (
                        AnswerEngine._person_inventory_heading(len(people), len(groups))
                        + "\n\n"
                        + "\n".join(
                            AnswerEngine._person_group_line(group) for group in groups
                        )
                    )
                else:
                    content = "Kanonik kayıtlardaki bilinen yapılandırılmış sonuç aşağıdadır."
        else:
            content = "Kanonik kayıtlardaki bilinen yapılandırılmış sonuç elde edildi."
        examples = ", ".join(f"“{item.raw_text}”" for item in query.evidence_refs[:2])
        return (
            content
            + "\n\nBu sonuç kısmi: kimliği henüz çözülememiş kanıt, kapsamlı sonucu değiştirebilir."
            + (f" İlgili kayıt: {examples}." if examples else "")
        )

    @staticmethod
    def _person_rows(package: ReasoningPackage):
        return [
            item
            for item in package.structured_rows
            if item.values.get("entity_type") == "person" and item.values.get("display_name")
        ]

    @staticmethod
    def _person_label(item, presentations) -> str:
        entity_id = str(item.values.get("entity_id") or item.item_id)
        presentation = presentations.get(entity_id)
        return presentation.display_label if presentation else str(item.values["display_name"])

    @staticmethod
    def _person_inventory_heading(candidate_count: int, visible_name_count: int) -> str:
        return (
            f"Kanonik kayıtlarda {candidate_count} kimlik adayı ve "
            f"{visible_name_count} farklı kişi adı görünümü var:"
        )

    @staticmethod
    def _person_group_line(group) -> str:
        if group.candidate_count == 1:
            return f"- {group.display_name}"
        return (
            f"- {group.display_name} — {group.candidate_count} ayrı kanonik kimlik adayı "
            "(aynı kişi olduklarını doğrulayan yeterli kanıt yok)"
        )
