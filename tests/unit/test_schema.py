"""Check ordered SQLite migrations, backups and version guards."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from przepisnik.core.schema import DATABASE_VERSION, MIGRATIONS, initialize_schema
from przepisnik.errors import StoreError


@pytest.fixture
def database(tmp_path: Path) -> Iterator[tuple[sqlite3.Connection, Path]]:
    """Return a connection to a new database file and its path."""
    path = tmp_path / "recipes.sqlite3"
    with closing(sqlite3.connect(path)) as connection:
        yield connection, path


def _version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def _tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {str(row[0]) for row in rows}


def test_new_database_gets_all_migrations(database: tuple[sqlite3.Connection, Path]) -> None:
    """Create every table without a backup of the empty file."""
    connection, path = database
    initialize_schema(connection, path, read_only=False)
    assert _version(connection) == DATABASE_VERSION
    assert {"recipes", "sources", "imported_items", "app_state"} <= _tables(connection)
    assert not list(path.parent.glob("*.bak"))
    initialize_schema(connection, path, read_only=False)
    assert _version(connection) == DATABASE_VERSION


def test_older_database_is_backed_up_and_upgraded(
    database: tuple[sqlite3.Connection, Path],
) -> None:
    """Keep a copy of the previous version before migrating."""
    connection, path = database
    for statement in MIGRATIONS[0]:
        connection.execute(statement)
    connection.execute("PRAGMA user_version = 1")
    connection.commit()
    initialize_schema(connection, path, read_only=False)
    assert _version(connection) == DATABASE_VERSION
    assert "app_state" in _tables(connection)
    backup = path.with_name(f"{path.name}.before-v{DATABASE_VERSION}.bak")
    with closing(sqlite3.connect(backup)) as copy:
        assert _version(copy) == 1
        assert "app_state" not in _tables(copy)


def test_newer_database_is_refused(database: tuple[sqlite3.Connection, Path]) -> None:
    """Never open a database written by a newer program version."""
    connection, path = database
    connection.execute(f"PRAGMA user_version = {DATABASE_VERSION + 1}")
    with pytest.raises(StoreError, match="Unsupported database version"):
        initialize_schema(connection, path, read_only=False)


def test_read_only_open_requires_current_schema(
    database: tuple[sqlite3.Connection, Path],
) -> None:
    """Refuse to upgrade a database opened for reading."""
    connection, path = database
    with pytest.raises(StoreError, match="upgrade required"):
        initialize_schema(connection, path, read_only=True)


def test_failed_migration_rolls_back(
    database: tuple[sqlite3.Connection, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Leave the database untouched when a migration statement fails."""
    connection, path = database
    monkeypatch.setattr(
        "przepisnik.core.schema.MIGRATIONS", ((*MIGRATIONS[0], "INVALID SQL"), *MIGRATIONS[1:])
    )
    with pytest.raises(sqlite3.OperationalError):
        initialize_schema(connection, path, read_only=False)
    with closing(sqlite3.connect(path)) as reopened:
        assert _version(reopened) == 0
        assert _tables(reopened) == set()
