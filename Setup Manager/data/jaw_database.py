import sqlite3
from pathlib import Path

from .migrations import migrate_jaws_schema


class JawDatabase:
    """Lightweight database wrapper for the jaws-only SQLite file."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        migrate_jaws_schema(self.conn)

    def close(self):
        self.conn.close()
