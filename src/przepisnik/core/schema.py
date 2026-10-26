"""Ordered, atomic SQLite schema migrations independent of recipe format versions."""

import sqlite3
from contextlib import closing
from pathlib import Path

from przepisnik.errors import StoreError

MIGRATIONS: tuple[tuple[str, ...], ...] = (
    (
        "CREATE TABLE recipes (id TEXT PRIMARY KEY, title_key TEXT NOT NULL, "
        "payload TEXT NOT NULL CHECK(json_valid(payload)))",
        "CREATE INDEX recipes_title ON recipes(title_key)",
        "CREATE TABLE sources (key TEXT PRIMARY KEY, "
        "payload TEXT NOT NULL CHECK(json_valid(payload)))",
        "CREATE TABLE imported_items (source_key TEXT NOT NULL, fingerprint TEXT NOT NULL, "
        "original_variant TEXT NOT NULL CHECK(original_variant IN ('male', 'female', 'family')), "
        "recipe_id TEXT NOT NULL REFERENCES recipes(id), "
        "PRIMARY KEY(source_key, fingerprint, original_variant))",
        "CREATE INDEX imported_content ON imported_items(fingerprint, original_variant)",
    ),
    ("CREATE TABLE IF NOT EXISTS app_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)",),
)
DATABASE_VERSION = len(MIGRATIONS)


def initialize_schema(connection: sqlite3.Connection, path: Path, *, read_only: bool) -> None:
    """Back up existing databases and apply pending migrations in one transaction.

    Append a tuple of statements to MIGRATIONS for each future schema version.
    Never edit released entries or use executescript, which commits implicitly.
    Read-only operations require an already current database.
    """
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version > DATABASE_VERSION:
        connection.close()
        raise StoreError(f"Unsupported database version: {version}")
    if version == DATABASE_VERSION:
        return
    if read_only:
        connection.close()
        raise StoreError("Database upgrade required; open it in writable mode first.")
    if version:
        backup = path.with_name(f"{path.name}.before-v{DATABASE_VERSION}.bak")
        if not backup.exists():
            with closing(sqlite3.connect(backup)) as destination:
                connection.backup(destination)
    try:
        connection.execute("BEGIN IMMEDIATE")
        # Another process may have upgraded the database while we waited for the lock.
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > DATABASE_VERSION:
            raise StoreError(f"Unsupported database version: {version}")
        for index in range(version, DATABASE_VERSION):
            for statement in MIGRATIONS[index]:
                connection.execute(statement)
            connection.execute(f"PRAGMA user_version = {index + 1}")
        connection.commit()
    except BaseException:
        connection.rollback()
        connection.close()
        raise
