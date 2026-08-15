"""Deterministic answer-stage evidence selection.

This intentionally runs after broad HybridRetriever candidate generation.  It never changes
dense, BM25, fusion, or reranker rank; it decides only which evidence is safe and useful to
give the answer builder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..core.config import get_settings
from ..retrieval.schemas import Evidence
from .query_plan import QueryPlan

_DESCRIPTIVE = (
    "malik", "hisse", "tapu", "miras", "tescil", "vekal", "vekâlet", "icra",
    "aile", "oğlu", "kızı", "mülkiyet", "hissedar", "temsil", "avukat",
)
_NUMERIC_LINE = re.compile(r"(?:^|\s)(?:[\d.,:/-]+\s*){2,}(?:$|\s)")
_TOKENS = re.compile(r"[\wÇĞİÖŞÜçğıöşü]+", re.UNICODE)


@dataclass(frozen=True)
class SelectionItem:
    evidence: Evidence
    score: float
    signals: tuple[str, ...]
    selected: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "chunk_id": self.evidence.chunk_id or "",
            "document_id": self.evidence.document_id or "",
            "score": round(self.score, 2),
            "selected": self.selected,
            "signals": list(self.signals),
        }


def final_evidence_limit(operation: str) -> int:
    settings = get_settings()
    return {
        "identify": settings.identify_final_evidence_top_k,
        "describe": settings.describe_final_evidence_top_k,
        "timeline": settings.timeline_final_evidence_top_k,
    }.get(operation, settings.final_evidence_top_k)


def _identity(item: Evidence) -> str:
    return (
        item.metadata.get("logical_document_id")
        or item.document_id
        or item.document_version_id
        or item.source
    )


def _score(item: Evidence, plan: QueryPlan) -> SelectionItem:
    text = item.content.casefold()
    tokens = _TOKENS.findall(text)
    alpha = sum(token.isalpha() for token in tokens)
    digits = sum(char.isdigit() for char in item.content)
    signals: list[str] = []
    score = float(item.score)
    entity = plan.entities[0] if plan.entities else None
    resolved = entity.resolved_value.casefold() if entity and entity.resolved_value else ""
    mention = entity.mention.casefold() if entity else ""
    if resolved and resolved in text:
        score += 8.0
        signals.append("resolved_full_name")
    elif mention and mention in text:
        score += 0.5
        signals.append("alias_only")
    if any(term in text for term in _DESCRIPTIVE):
        score += 2.0
        signals.append("descriptive_context")
    if len(tokens) >= 16 and alpha >= 10:
        score += 1.0
        signals.append("substantive_context")
    numeric_heavy = digits >= max(5, alpha) or bool(_NUMERIC_LINE.search(item.content))
    if numeric_heavy:
        penalty = 4.0 if plan.operation in {"identify", "describe", "timeline"} else 0.5
        score -= penalty
        signals.append("numeric_shorthand")
    if len(tokens) < 5 or (alpha < 4 and not resolved):
        score -= 3.0
        signals.append("stub_or_fragment")
    if resolved and resolved not in text and mention and mention not in text:
        score -= 3.0
        signals.append("entity_not_present")
    elif resolved and resolved not in text and plan.operation == "identify":
        score -= 1.5
        signals.append("no_full_name_context")
    return SelectionItem(item, score, tuple(signals))


def select_answer_evidence(
    evidence: list[Evidence], plan: QueryPlan
) -> tuple[list[Evidence], dict[str, object]]:
    """Rank answer evidence, reject weak identity material, and prefer document diversity."""
    scored = sorted(
        (_score(item, plan) for item in evidence), key=lambda item: item.score, reverse=True
    )
    limit = final_evidence_limit(plan.operation)
    selected: list[Evidence] = []
    selected_ids: set[str] = set()
    for item in scored:
        # Identity answers must not be padded with stubs or another person's numeric record.
        if plan.operation == "identify":
            weak_identity = (
                "entity_not_present" in item.signals
                or "stub_or_fragment" in item.signals
                or (
                    "numeric_shorthand" in item.signals
                    and "resolved_full_name" not in item.signals
                )
            )
            if weak_identity or item.score < 0:
                continue
        identity = _identity(item.evidence)
        if identity in selected_ids:
            continue
        selected.append(item.evidence)
        selected_ids.add(identity)
        if len(selected) >= limit:
            break
    selected_keys = {item.chunk_id or f"{item.source}:{item.content}" for item in selected}
    trace_items = [
        SelectionItem(
            item.evidence,
            item.score,
            item.signals,
            (item.evidence.chunk_id or f"{item.evidence.source}:{item.evidence.content}")
            in selected_keys,
        ).as_dict()
        for item in scored
    ]
    entity = plan.entities[0] if plan.entities else None
    return selected, {
        "operation": plan.operation,
        "resolved_entity": entity.resolved_value if entity else None,
        "input_count": len(evidence),
        "selected_count": len(selected),
        "limit": limit,
        "items": trace_items,
    }
