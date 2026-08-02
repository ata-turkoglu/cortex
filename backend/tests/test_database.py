import sqlite3

from app.core.database import configure_sqlite


def test_sqlite_connection_pragmas_are_applied():
    connection = sqlite3.connect(":memory:")
    configure_sqlite(connection, None)
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert connection.execute("PRAGMA busy_timeout").fetchone()[0] > 0
    connection.close()
