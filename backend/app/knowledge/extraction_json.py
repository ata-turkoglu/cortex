"""Strict JSON decoder for provider-produced knowledge extraction bundles."""

import json
from typing import Any

from .extraction import (
    ExtractedClaim,
    ExtractedEvent,
    ExtractedMention,
    ExtractedRelation,
    ExtractedSpan,
    ExtractedTemporal,
    ExtractionMetadata,
    KnowledgeExtractionBundle,
)


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _list(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return value


def _string(row: dict[str, Any], name: str) -> str:
    value = row.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _integer(row: dict[str, Any], name: str) -> int:
    value = row.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    return value


def _confidence(row: dict[str, Any]) -> float:
    value = row.get("confidence")
    if not isinstance(value, int | float) or isinstance(value, bool) or not 0 <= value <= 1:
        raise ValueError("confidence must be a number between zero and one")
    return float(value)


def _span(row: dict[str, Any]) -> ExtractedSpan:
    return ExtractedSpan(
        chunk_id=_string(row, "chunk_id"),
        start_offset=_integer(row, "start_offset"),
        end_offset=_integer(row, "end_offset"),
        source_text=_string(row, "source_text"),
        confidence=_confidence(row),
    )


def _rows(payload: dict[str, Any], name: str) -> list[dict[str, Any]]:
    return [_object(item, f"{name} item") for item in _list(payload.get(name, []), name)]


def decode_extraction_json(text: str, metadata: ExtractionMetadata) -> KnowledgeExtractionBundle:
    """Decode only the provider schema; exact source validation happens against a snapshot later."""
    try:
        payload = _object(json.loads(text), "extraction payload")
    except json.JSONDecodeError as exc:
        raise ValueError("knowledge extraction response must be valid JSON") from exc
    mentions = tuple(
        ExtractedMention(_string(row, "id"), _string(row, "entity_type"), _span(row))
        for row in _rows(payload, "mentions")
    )
    relations = tuple(
        ExtractedRelation(
            _string(row, "relation_type"),
            _string(row, "source_mention_id"),
            _string(row, "target_mention_id"),
            _span(row),
        )
        for row in _rows(payload, "relations")
    )
    events = tuple(
        ExtractedEvent(
            _string(row, "id"),
            _string(row, "event_type"),
            tuple(
                _string(_object(item, "event participant"), "mention_id")
                for item in _list(row.get("participants", []), "participants")
            ),
            _span(row),
        )
        for row in _rows(payload, "events")
    )
    temporals = tuple(
        ExtractedTemporal(
            _string(row, "id"),
            _string(row, "original_text"),
            row.get("normalized_start") if isinstance(row.get("normalized_start"), str) else None,
            row.get("normalized_end") if isinstance(row.get("normalized_end"), str) else None,
            _string(row, "semantic_role"),
            _string(row, "precision"),
            bool(row.get("uncertain")),
            _span(row),
        )
        for row in _rows(payload, "temporals")
    )
    claims = tuple(
        ExtractedClaim(
            _string(row, "subject_mention_id"),
            _string(row, "predicate"),
            row.get("value"),
            _span(row),
        )
        for row in _rows(payload, "claims")
    )
    return KnowledgeExtractionBundle(metadata, mentions, relations, events, temporals, claims)
