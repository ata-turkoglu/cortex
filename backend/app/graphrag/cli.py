"""Worker-only compatibility entry point for the upstream GraphRAG CLI."""

from __future__ import annotations

import sys
from typing import Any


def normalize_arrow_values(table):
    """Convert Arrow arrays nested in object cells into Parquet-safe Python lists.

    GraphRAG 2.6's final text-unit workflow stores the result of pandas ``unique``
    directly in ``entity_ids`` and related columns. With Arrow-backed values,
    pandas cannot infer a Parquet type for those object cells. The canonical rows
    are preserved; only their in-memory container is normalized before upstream
    writes its native Parquet artifact.
    """
    import pyarrow as pa

    for column in table.columns:
        if table[column].dtype != "object":
            continue
        if table[column].map(lambda value: isinstance(value, pa.Array | pa.ChunkedArray)).any():
            table = table.copy()
            table[column] = table[column].map(
                lambda value: value.to_pylist()
                if isinstance(value, pa.Array | pa.ChunkedArray)
                else value
            )
    return table


def preload_torch_on_windows():
    """Load PyTorch before GraphRAG's scientific stack on Windows.

    GraphRAG's import chain reaches PyTorch through graspologic. On Windows, loading that
    chain first can fail to initialize torch's ``c10.dll`` (WinError 1114), while loading
    PyTorch before it is reliable. Linux worker containers do not need this ordering shim.
    """
    if sys.platform != "win32":
        return None
    import torch

    return torch


def install_parquet_compatibility() -> None:
    """Patch only GraphRAG's final artifact writer for this worker process."""
    from graphrag.index.workflows import create_final_text_units
    from graphrag.utils import storage

    original = storage.write_table_to_storage

    async def write_table_to_storage(table: Any, name: str, target: Any) -> None:
        await original(normalize_arrow_values(table), name, target)

    storage.write_table_to_storage = write_table_to_storage
    create_final_text_units.write_table_to_storage = write_table_to_storage


def main() -> None:
    preload_torch_on_windows()
    install_parquet_compatibility()
    from graphrag.cli.main import app

    app(prog_name="graphrag")


if __name__ == "__main__":
    main()
