"""Persistent accounting for the trusted home instance of Kucharz AI."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from uuid import uuid4

BUDGET_MICRO_USD = 1_000_000


class ChefError(Exception):
    """A message safe to display in the chef panel."""


class ChefLedger:
    """Keep charges independent from draft expiry and recipe collection edits."""

    def __init__(self, directory: Path) -> None:
        """Use the instance data volume across server restarts."""
        self.path = directory / "chef.sqlite3"

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Open a short transaction without holding locks during provider calls."""
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS charges (id TEXT PRIMARY KEY, model TEXT NOT NULL,"
                " created INTEGER NOT NULL, reserved INTEGER NOT NULL, settled INTEGER)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS drafts (id TEXT PRIMARY KEY, created INTEGER NOT NULL,"
                " recipe TEXT NOT NULL)"
            )
            conn.execute("DELETE FROM drafts WHERE created < unixepoch() - 86400")
            yield conn

    def status(self) -> dict[str, int]:
        """Return conservative settled and outstanding costs in millionths of a dollar."""
        with self.connect() as conn:
            spent, held = conn.execute(
                "SELECT coalesce(sum(settled),0),"
                " coalesce(sum(CASE WHEN settled IS NULL THEN reserved END),0) FROM charges"
            ).fetchone()
        return {"spent": spent, "reserved": held, "available": BUDGET_MICRO_USD - spent - held}

    def reserve(self, model: str, maximum: int) -> str:
        """Serialize admission against the lifetime budget and instance rate limit."""
        charge = uuid4().hex
        with self.connect() as conn:
            total, recent = conn.execute(
                "SELECT coalesce(sum(coalesce(settled,reserved)),0),"
                " count(CASE WHEN created > unixepoch()-5 THEN 1 END) FROM charges"
            ).fetchone()
            if recent:
                raise ChefError("Odczekaj pięć sekund przed następną operacją AI.")
            if total + maximum > BUDGET_MICRO_USD:
                raise ChefError("Pozostały budżet nie wystarcza na tę operację.")
            conn.execute(
                "INSERT INTO charges VALUES (?,?,unixepoch(),?,NULL)", (charge, model, maximum)
            )
        return charge

    def settle(self, charge: str, amount: int) -> None:
        """Record a known charge, leaving ambiguous requests reserved indefinitely."""
        with self.connect() as conn:
            conn.execute("UPDATE charges SET settled=? WHERE id=?", (amount, charge))
        return None

    def remember(self, recipe: str) -> str:
        """Issue a fresh, independent preview identity."""
        identity = uuid4().hex
        with self.connect() as conn:
            conn.execute("INSERT INTO drafts VALUES (?,unixepoch(),?)", (identity, recipe))
        return identity

    def draft(self, identity: str) -> str:
        """Read a previous validated draft for revisions, illustrations or saving."""
        with self.connect() as conn:
            row = conn.execute("SELECT recipe FROM drafts WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise ChefError("Szkic wygasł lub został odrzucony.")
        return str(row[0])

    def discard(self, identity: str) -> None:
        """Drop only the temporary preview."""
        with self.connect() as conn:
            conn.execute("DELETE FROM drafts WHERE id=?", (identity,))
        return None
