"""Metadata precedence: user corrections override extracted and system values."""

from collections.abc import Iterable


ORIGIN_PRECEDENCE = {"system": 0, "extracted": 1, "user": 2}


def effective_metadata(rows: Iterable[tuple[str, str, object]]) -> dict[str, object]:
    result: dict[str, tuple[int, object]] = {}
    for key, origin, value in rows:
        if origin not in ORIGIN_PRECEDENCE:
            raise ValueError("invalid metadata origin")
        if key not in result or ORIGIN_PRECEDENCE[origin] >= result[key][0]:
            result[key] = (ORIGIN_PRECEDENCE[origin], value)
    return {key: value for key, (_, value) in result.items()}
