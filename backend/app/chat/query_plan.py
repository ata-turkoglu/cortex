"""Validated compositional query plans and workspace-grounded entity resolution."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Chunk, DocumentMetadata

Operation = Literal[
    "identify", "describe", "lookup_documents", "list", "count", "timeline", "compare", "generic_qa"
]
EntityType = Literal["person", "organization", "place", "property", "document", "unknown"]
_MAX_CANDIDATE_CHUNKS = 5_000
_MAX_CANDIDATES = 12
_PERSON_NAME = re.compile(
    r"(?<!\w)(?:[A-ZÇĞİÖŞÜ][\w'’.-]{1,}\s+){1,3}[A-ZÇĞİÖŞÜ][\w'’.-]{1,}(?!\w)", re.UNICODE
)
_HONORIFIC = re.compile(r"^(?:dr|prof|av|mr|mrs|ms)\.?\s+", re.IGNORECASE)
_WEAK_NUMERIC = re.compile(r"(?:^|\s)\d[\d. ,/-]{5,}(?:\s|$)")
_DESCRIPTIVE_TERMS = ("malik", "hisse", "tapu", "miras", "vekal", "tescil", "gayrimenkul")


@dataclass(frozen=True)
class EntityCandidate:
    value: str
    score: float
    document_count: int
    chunk_count: int
    aliases: tuple[str, ...]
    basis: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "score": self.score,
            "document_count": self.document_count,
            "chunk_count": self.chunk_count,
            "aliases": list(self.aliases),
            "basis": list(self.basis),
        }


@dataclass(frozen=True)
class QueryEntity:
    type: EntityType
    mention: str
    normalized: str
    resolved_value: str | None = None
    aliases: tuple[str, ...] = ()
    confidence: float = 0.0
    resolution_basis: tuple[str, ...] = ()
    candidates: tuple[EntityCandidate, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "type": self.type,
            "mention": self.mention,
            "normalized": self.normalized,
            "resolved_value": self.resolved_value,
            "aliases": list(self.aliases),
            "confidence": self.confidence,
            "resolution_basis": list(self.resolution_basis),
            "candidates": [candidate.as_dict() for candidate in self.candidates],
        }


@dataclass(frozen=True)
class DateConstraint:
    date_start: str | None = None
    date_end: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {"date_start": self.date_start, "date_end": self.date_end}


@dataclass(frozen=True)
class QueryPlan:
    operation: Operation
    entities: tuple[QueryEntity, ...] = ()
    constraints: DateConstraint = field(default_factory=DateConstraint)
    scope: str = "relevant_evidence"
    retrieval_strategy: str = "hybrid"
    requires_exhaustive_retrieval: bool = False
    requires_aggregation: bool = False
    requires_deduplication: bool = False
    confidence: float = 0.6
    reason: str = "Deterministic structured query planner."

    def as_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "entities": [entity.as_dict() for entity in self.entities],
            "constraints": self.constraints.as_dict(),
            "scope": self.scope,
            "retrieval_strategy": self.retrieval_strategy,
            "requires_exhaustive_retrieval": self.requires_exhaustive_retrieval,
            "requires_aggregation": self.requires_aggregation,
            "requires_deduplication": self.requires_deduplication,
            "confidence": self.confidence,
            "reason": self.reason,
        }


_YEAR_RANGE = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\s*[-–]\s*(1[0-9]{3}|20[0-9]{2})\b")
_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})(?:\s*(?:yılında|de|da))?\b", re.I)
_QUESTION_SUFFIX = re.compile(
    r"\s*(?:kim(?:dir)?|hakkında\s+(?:neler|ne)\s+biliyoruz|hakkında|hangi\s+(?:belgelerde|dosyalarda)\s+geç(?:iyor|mektedir)?|(?:hangi|tüm)\s+(?:malları|gayrimenkulleri)\s+(?:var|nelerdir)|kaç\s+adet\s+(?:tapusu|gayrimenkulü)\s+var|ile\s+ilgili\s+ne\s+olmuş)\s*$",
    re.I,
)


def _operation(query: str) -> tuple[Operation, bool, bool, bool]:
    value = query.casefold()
    if re.search(
        r"hangi\s+(?:belge|dosya)|(?:belge|dosya)lerde\s+geç|documents?\s+(?:containing|mentioning)",
        value,
    ):
        return "lookup_documents", False, False, False
    if re.search(r"kaç\s+(?:adet|tane)|how many", value):
        return "count", True, True, True
    if re.search(
        r"(?:hangi|tüm)\s+(?:mal|gayrimenkul)|(?:malları|gayrimenkulleri)\s+(?:var|nelerdir)", value
    ):
        return "list", True, False, True
    if _YEAR.search(value):
        return "timeline", False, False, False
    if re.search(r"\bkim(?:dir)?\b|who is", value):
        return "identify", False, False, False
    if re.search(r"hakkında|neler biliyoruz|tell me about|what do we know", value):
        return "describe", False, False, False
    return "generic_qa", False, False, False


def _constraint(query: str) -> DateConstraint:
    if match := _YEAR_RANGE.search(query):
        return DateConstraint(match.group(1), match.group(2))
    if match := _YEAR.search(query):
        return DateConstraint(match.group(1), match.group(1))
    return DateConstraint()


def _mention(query: str, operation: Operation) -> str | None:
    value = " ".join(query.strip().strip("?!.").split())
    if operation == "lookup_documents":
        value = re.sub(
            r"\s+hangi\s+(?:belgelerde|dosyalarda)\s+geç(?:iyor|mektedir)?\??$",
            "",
            value,
            flags=re.I,
        )
    if operation in {"list", "count"}:
        value = re.sub(
            r"(?:(?:'|’)(?:in|ın|un|ün)|(?:nin|nın|nun|nün))\s+.*$", "", value, flags=re.I
        )
    value = _QUESTION_SUFFIX.sub("", value).strip(" ?!.'")
    return value if value and len(value) <= 120 else None


def plan_query(query: str) -> QueryPlan:
    operation, exhaustive, aggregation, deduplication = _operation(query)
    mention = _mention(query, operation)
    entities = () if not mention else (QueryEntity("person", mention, _normalize(mention)),)
    return QueryPlan(
        operation,
        entities,
        _constraint(query),
        requires_exhaustive_retrieval=exhaustive,
        requires_aggregation=aggregation,
        requires_deduplication=deduplication,
        confidence=0.72 if operation != "generic_qa" else 0.5,
    )


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFC", _HONORIFIC.sub("", value)).casefold()


def _aliases(mention: str, rows: list[tuple[str, str]]) -> tuple[str, ...]:
    found = {mention}
    pattern = re.compile(rf"\b(?:dr\.?\s*)?{re.escape(mention)}\b", re.I)
    for _, content in rows:
        found.update(match.group(0).strip() for match in pattern.finditer(content))
    return tuple(
        sorted(found, key=lambda value: (value.casefold() != mention.casefold(), value.casefold()))
    )


def _rank_candidates(
    mention: str, rows: list[tuple[str, str]], metadata_people: set[str]
) -> tuple[EntityCandidate, ...]:
    mention_tokens = set(_normalize(mention).split())
    support: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for document_id, content in rows:
        for match in _PERSON_NAME.finditer(content):
            value = match.group(0).strip()
            if (
                mention_tokens <= set(_normalize(value).split())
                and len(_normalize(value).split()) >= 2
            ):
                support[value].append((document_id, content))
    ranked: list[EntityCandidate] = []
    for value, matches in support.items():
        documents = {document_id for document_id, _ in matches}
        descriptive = any(
            any(term in content.casefold() for term in _DESCRIPTIVE_TERMS) for _, content in matches
        )
        metadata_confirmed = value in metadata_people
        score = (
            0.55
            + 0.18
            + min(0.12, 0.04 * len(documents))
            + min(0.08, 0.02 * len(matches))
            + (0.06 if descriptive else 0)
            + (0.08 if metadata_confirmed else 0)
        )
        if all(_WEAK_NUMERIC.search(content) for _, content in matches):
            score -= 0.18
        basis = [
            "mention is an exact full-name token",
            f"supported by {len(documents)} document(s)",
        ]
        if descriptive:
            basis.append("descriptive ownership or legal context")
        if metadata_confirmed:
            basis.append("metadata people value")
        ranked.append(
            EntityCandidate(
                value,
                round(max(0.0, min(score, 0.99)), 2),
                len(documents),
                len(matches),
                _aliases(mention, rows),
                tuple(basis),
            )
        )
    return tuple(
        sorted(ranked, key=lambda item: (-item.score, -item.document_count, item.value))[
            :_MAX_CANDIDATES
        ]
    )


def resolve_entities(session: Session, workspace_id: str, plan: QueryPlan) -> QueryPlan:
    """Resolve against bounded active workspace evidence and preserve diagnostic trace."""
    rows = [
        (str(document_id), content)
        for document_id, content in session.execute(
            select(Chunk.document_id, Chunk.content)
            .where(Chunk.workspace_id == workspace_id, Chunk.deleted_at.is_(None))
            .limit(_MAX_CANDIDATE_CHUNKS)
        ).all()
    ]
    metadata_people = {
        match.group(0).strip()
        for value in session.scalars(
            select(DocumentMetadata.value_json).where(DocumentMetadata.workspace_id == workspace_id)
        ).all()
        for match in _PERSON_NAME.finditer(value)
    }
    resolved: list[QueryEntity] = []
    for entity in plan.entities:
        candidates = _rank_candidates(entity.mention, rows, metadata_people)
        winner = candidates[0] if candidates else None
        ambiguous = bool(
            winner and len(candidates) > 1 and winner.score - candidates[1].score < 0.08
        )
        if winner and winner.score >= 0.72 and not ambiguous:
            resolved.append(
                QueryEntity(
                    entity.type,
                    entity.mention,
                    entity.normalized,
                    winner.value,
                    winner.aliases,
                    winner.score,
                    winner.basis,
                    candidates,
                )
            )
        else:
            basis = (
                ("multiple similarly supported candidates",)
                if ambiguous
                else ("no sufficiently supported full-name candidate",)
            )
            resolved.append(
                QueryEntity(
                    entity.type,
                    entity.mention,
                    entity.normalized,
                    None,
                    _aliases(entity.mention, rows),
                    0.0,
                    basis,
                    candidates,
                )
            )
    return QueryPlan(**{**plan.__dict__, "entities": tuple(resolved)})


def entity_resolution_trace(plan: QueryPlan) -> list[dict[str, object]]:
    return [
        {
            "mention": entity.mention,
            "resolved_value": entity.resolved_value,
            "confidence": entity.confidence,
            "aliases": list(entity.aliases),
            "candidates": [candidate.as_dict() for candidate in entity.candidates],
            "resolution_basis": list(entity.resolution_basis),
        }
        for entity in plan.entities
    ]


def retrieval_queries(query: str, plan: QueryPlan) -> list[str]:
    values = [query]
    for entity in plan.entities:
        if entity.mention.casefold() != query.casefold():
            values.append(entity.mention)
        if entity.resolved_value:
            values.append(entity.resolved_value)
        if plan.constraints.date_start and entity.resolved_value:
            values.append(f"{entity.resolved_value} {plan.constraints.date_start}")
    return list(dict.fromkeys(value for value in values if value.strip()))
