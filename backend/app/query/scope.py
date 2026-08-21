"""Immutable V2 knowledge snapshot identity resolved once per query."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GenerationScope:
    workspace_id: str
    generation_id: str
    embedding_config_hash: str

    def __post_init__(self) -> None:
        if not all(value.strip() for value in self.__dict__.values()):
            raise ValueError("GENERATION_SCOPE_REQUIRED")
