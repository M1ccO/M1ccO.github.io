from pathlib import Path

from shared.data.base_database import BaseSqliteDatabase

from .migrations import migrate_fixtures_schema


class FixtureDatabase(BaseSqliteDatabase):
    """Lightweight database wrapper for the fixtures-only SQLite file."""

    def __init__(self, path: Path):
        super().__init__(path, ensure_parent=True)
        migrate_fixtures_schema(self.conn)
