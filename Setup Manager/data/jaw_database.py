from pathlib import Path

from shared.data.base_database import BaseSqliteDatabase

from .migrations import migrate_jaws_schema


class JawDatabase(BaseSqliteDatabase):
    """Lightweight database wrapper for the jaws-only SQLite file."""

    def __init__(self, path: Path):
        super().__init__(path, ensure_parent=True)
        migrate_jaws_schema(self.conn)
