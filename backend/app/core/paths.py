from pathlib import Path


def normalized_data_path(value: str, root: Path) -> Path:
    candidate = Path(value).expanduser().resolve()
    allowed = root.resolve()
    if candidate != allowed and allowed not in candidate.parents:
        raise ValueError("data path must remain under the configured data root")
    return candidate
