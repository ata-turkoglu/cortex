"""Evidence-honest presentation for canonical Person result rows."""

from __future__ import annotations

import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from .orchestration import GroundedItem


@dataclass(frozen=True)
class CanonicalPersonPresentation:
    """One user-facing label while retaining the canonical row identity.

    A collision means multiple durable canonical records have the same visible
    name. It is not evidence that they denote distinct real-world people.
    """

    canonical_entity_id: str
    original_preferred_name: str
    display_name: str
    display_label: str
    same_name_candidate_count: int


@dataclass(frozen=True)
class CanonicalPersonDisplayGroup:
    """A visible-name group that never silently merges canonical identities."""

    display_name: str
    canonical_entity_ids: tuple[str, ...]

    @property
    def candidate_count(self) -> int:
        return len(self.canonical_entity_ids)


def build_canonical_person_presentations(
    rows: Iterable[GroundedItem],
) -> dict[str, CanonicalPersonPresentation]:
    """Build deterministic labels for Person rows with colliding visible names.

    The label makes an unresolved duplicate explicit. It does not merge
    identities or alter query membership/counts.
    """
    candidates = [
        _candidate(row)
        for row in rows
        if row.values.get("entity_type") == "person"
        and isinstance(row.values.get("display_name"), str)
    ]
    candidates = [item for item in candidates if item is not None]
    collisions = Counter(item.display_name.casefold() for item in candidates)
    presentations: dict[str, CanonicalPersonPresentation] = {}
    for collision_key in sorted(collisions):
        group = sorted(
            (item for item in candidates if item.display_name.casefold() == collision_key),
            key=lambda item: (item.display_name.casefold(), item.canonical_entity_id),
        )
        for ordinal, item in enumerate(group, start=1):
            label = (
                f"{item.display_name} (kimlik adayı {ordinal}/{len(group)})"
                if collisions[collision_key] > 1
                else item.display_name
            )
            presentations[item.canonical_entity_id] = CanonicalPersonPresentation(
                canonical_entity_id=item.canonical_entity_id,
                original_preferred_name=item.original_preferred_name,
                display_name=item.display_name,
                display_label=label,
                same_name_candidate_count=len(group),
            )
    return presentations


def group_canonical_person_presentations(
    rows: Iterable[GroundedItem],
) -> tuple[CanonicalPersonDisplayGroup, ...]:
    """Group exact visible-name collisions for a person inventory.

    This is presentation grouping, not canonical identity resolution. The
    caller can show a name once while preserving the unresolved candidate count.
    """
    presentations = build_canonical_person_presentations(rows)
    ordered: dict[str, list[str]] = {}
    names: dict[str, str] = {}
    for row in rows:
        entity_id = str(row.values.get("entity_id") or row.item_id)
        presentation = presentations.get(entity_id)
        if presentation is None:
            continue
        key = presentation.display_name.casefold()
        ordered.setdefault(key, []).append(entity_id)
        names.setdefault(key, presentation.display_name)
    return tuple(
        CanonicalPersonDisplayGroup(names[key], tuple(entity_ids))
        for key, entity_ids in ordered.items()
    )


def normalize_person_display_case(value: str) -> str:
    """Normalize obvious archival all-upper/all-lower casing for display only."""
    normalized = " ".join(unicodedata.normalize("NFKC", value).split())
    cased = [character for character in normalized if character.isalpha()]
    if not cased or not (all(character.isupper() for character in cased) or all(
        character.islower() for character in cased
    )):
        return normalized
    return " ".join(_turkish_title(token) for token in normalized.split(" "))


def _candidate(row: GroundedItem) -> CanonicalPersonPresentation | None:
    original = str(row.values["display_name"])
    display_name = normalize_person_display_case(original)
    if not display_name:
        return None
    canonical_entity_id = str(row.values.get("entity_id") or row.item_id)
    return CanonicalPersonPresentation(
        canonical_entity_id=canonical_entity_id,
        original_preferred_name=original,
        display_name=display_name,
        display_label=display_name,
        same_name_candidate_count=1,
    )


def _turkish_title(token: str) -> str:
    if not token:
        return token
    return _turkish_upper(token[0]) + _turkish_lower(token[1:])


def _turkish_lower(value: str) -> str:
    return value.translate(str.maketrans({"I": "ı", "İ": "i"})).lower()


def _turkish_upper(value: str) -> str:
    return value.translate(str.maketrans({"i": "İ", "ı": "I"})).upper()
