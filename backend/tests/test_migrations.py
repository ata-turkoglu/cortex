"""Migration tests use an isolated, empty SQLite database."""

import sqlite3
import subprocess
import sys
from pathlib import Path


def test_migrations_apply_from_empty_database(tmp_path):
    database = tmp_path / "cortex.db"
    environment = {"CORTEX_DATABASE_URL": f"sqlite:///{database.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=Path(__file__).parents[1],
        env={**__import__("os").environ, **environment},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    connection = sqlite3.connect(database)
    indexes = connection.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'index' AND tbl_name = 'document_versions'"
    ).fetchall()
    connection.close()
    assert any(
        name == "ux_document_versions_workspace_active_source_hash"
        and "WHERE deleted_at IS NULL" in sql
        for name, sql in indexes
    )


def test_workspace_migration_preserves_phase_three_data(tmp_path):
    database = tmp_path / "upgrade.db"
    environment = {"CORTEX_DATABASE_URL": f"sqlite:///{database.as_posix()}"}
    command = [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade"]
    initial = subprocess.run(
        [*command, "0002_usage_records"],
        cwd=Path(__file__).parents[1],
        env={**__import__("os").environ, **environment},
        check=False,
        capture_output=True,
        text=True,
    )
    assert initial.returncode == 0, initial.stderr
    connection = sqlite3.connect(database)
    connection.execute("INSERT INTO schema_metadata (key, value) VALUES ('phase', 'three')")
    connection.commit()
    connection.close()
    upgraded = subprocess.run(
        [*command, "head"],
        cwd=Path(__file__).parents[1],
        env={**__import__("os").environ, **environment},
        check=False,
        capture_output=True,
        text=True,
    )
    assert upgraded.returncode == 0, upgraded.stderr
    connection = sqlite3.connect(database)
    assert (
        connection.execute("SELECT value FROM schema_metadata WHERE key = 'phase'").fetchone()[0]
        == "three"
    )
    connection.close()
