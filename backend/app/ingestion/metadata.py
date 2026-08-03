from collections.abc import Iterable

from ..core.config import get_settings

"""Metadata precedence: user corrections override extracted and system values."""


ORIGIN_PRECEDENCE = {"system": 0, "extracted": 1, "user": 2}


def effective_metadata(rows: Iterable[tuple[str, str, object]]) -> dict[str, object]:
    result: dict[str, tuple[int, object]] = {}
    for key, origin, value in rows:
        if origin not in ORIGIN_PRECEDENCE:
            raise ValueError("invalid metadata origin")
        if key not in result or ORIGIN_PRECEDENCE[origin] >= result[key][0]:
            result[key] = (ORIGIN_PRECEDENCE[origin], value)
    return {key: value for key, (_, value) in result.items()}


def metadata_extraction_assignment() -> tuple[str, str]:
    """Resolve the global assignment for worker-owned metadata extraction."""
    settings = get_settings()
    return settings.metadata_provider, settings.metadata_model
