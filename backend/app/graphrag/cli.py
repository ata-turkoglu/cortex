"""Worker-only compatibility entry point for the upstream GraphRAG CLI."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pyarrow as pa


def normalize_arrow_values(table: pd.DataFrame) -> pd.DataFrame:
    """Convert Arrow arrays nested in object cells into Parquet-safe Python lists.

    GraphRAG 2.6's final text-unit workflow stores the result of pandas ``unique``
    directly in ``entity_ids`` and related columns. With Arrow-backed values,
    pandas cannot infer a Parquet type for those object cells. The canonical rows
    are preserved; only their in-memory container is normalized before upstream
    writes its native Parquet artifact.
    """
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


def install_parquet_compatibility() -> None:
    """Patch only GraphRAG's final artifact writer for this worker process."""
    from graphrag.index.workflows import create_final_text_units
    from graphrag.utils import storage

    original = storage.write_table_to_storage

    async def write_table_to_storage(table: pd.DataFrame, name: str, target: Any) -> None:
        await original(normalize_arrow_values(table), name, target)

    storage.write_table_to_storage = write_table_to_storage
    create_final_text_units.write_table_to_storage = write_table_to_storage


def main() -> None:
    install_parquet_compatibility()
    from graphrag.cli.main import app

    app(prog_name="graphrag")


if __name__ == "__main__":
    main()
