"""Bounded workspace knowledge supplied to V2 planning and deterministic resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .understanding import SemanticEntity, SemanticUnderstanding


@dataclass(frozen=True)
class WorkspaceEntityCandidate:
    entity_id: str
    entity_type: str
    display_name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkspaceBriefing:
    workspace_id: str
    generation_id: str
    entities: tuple[WorkspaceEntityCandidate, ...]

    def planner_context(self) -> dict[str, object]:
        """Bounded planner input: identities only, never source text or unscoped graph data."""
        return {
            "workspace_id": self.workspace_id,
            "generation_id": self.generation_id,
            "canonical_entities": [
                {
                    "entity_id": item.entity_id,
                    "entity_type": item.entity_type,
                    "display_name": item.display_name,
                    "aliases": list(item.aliases),
                }
                for item in self.entities
            ],
        }


class GenerationEntityReader(Protocol):
    workspace_id: str

    def list_generation_entities(
        self, generation: str, limit: int = 100
    ) -> tuple[object, ...]: ...


def build_workspace_briefing(
    reader: GenerationEntityReader, generation_id: str, *, limit: int = 100
) -> WorkspaceBriefing:
    """Read a bounded, generation-scoped identity catalogue outside SQLite work."""
    if not generation_id.strip() or not 1 <= limit <= 500:
        raise ValueError("generation and a bounded limit are required")
    return WorkspaceBriefing(
        workspace_id=reader.workspace_id,
        generation_id=generation_id,
        entities=tuple(
            WorkspaceEntityCandidate(
                entity_id=item.entity_id,
                entity_type=item.entity_type,
                display_name=item.display_name,
                aliases=tuple(item.aliases),
            )
            for item in reader.list_generation_entities(generation_id, limit)
        ),
    )


def resolve_workspace_entities(
    understanding: SemanticUnderstanding, briefing: WorkspaceBriefing
) -> SemanticUnderstanding:
    """Resolve only unique exact display-name or alias matches; everything else stays explicit."""
    entities = []
    unresolved = list(understanding.unresolved_questions)
    for entity in understanding.entities:
        if entity.resolution == "resolved":
            entities.append(entity)
            continue
        matches = _matches(entity, briefing)
        if len(matches) == 1:
            match = matches[0]
            entities.append(
                entity.model_copy(
                    update={
                        "resolution": "resolved",
                        "canonical_entity_id": match.entity_id,
                        "display_name": match.display_name,
                        "candidate_entity_ids": (),
                    }
                )
            )
        else:
            entities.append(entity)
            if len(matches) > 1:
                unresolved.append(
                    f"Which {entity.mention} do you mean? Multiple canonical identities match."
                )
    payload = understanding.model_dump(mode="json")
    payload["entities"] = [item.model_dump(mode="json") for item in entities]
    if entities and all(item.resolution == "resolved" for item in entities):
        payload.update(
            state="resolved", candidates=[], ambiguity_reasons=[], unresolved_questions=[]
        )
    elif unresolved:
        payload.update(
            state="unresolved",
            candidates=[],
            ambiguity_reasons=[],
            unresolved_questions=list(dict.fromkeys(unresolved))[:10],
        )
    return SemanticUnderstanding.model_validate(payload)


def _matches(
    entity: SemanticEntity, briefing: WorkspaceBriefing
) -> tuple[WorkspaceEntityCandidate, ...]:
    normalized = entity.mention.strip().casefold()
    return tuple(
        candidate
        for candidate in briefing.entities
        if (entity.entity_type == "unknown" or candidate.entity_type == entity.entity_type)
        and normalized in _candidate_names(candidate)
    )


def _candidate_names(candidate: WorkspaceEntityCandidate) -> set[str]:
    return {
        candidate.display_name.strip().casefold(),
        *(alias.strip().casefold() for alias in candidate.aliases),
    }
