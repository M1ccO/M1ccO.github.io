"""Shared SQLite connection lifecycle base class.

Provides the neutral connection/lifecycle primitive used by both apps'
Database and JawDatabase classes.  App‑specific schemas and migrations
remain in each app's ``data/migrations.py``.
"""

import sqlite3
from pathlib import Path


class BaseSqliteDatabase:
    """Thin wrapper around a sqlite3 connection with row_factory = Row."""

    def __init__(self, path: Path, *, ensure_parent: bool = False):
        self.path = Path(path)
        if ensure_parent:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row

    def close(self):
        self.conn.close()
