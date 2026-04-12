from pathlib import Path

from shared.data.base_database import BaseSqliteDatabase

from .migrations import create_or_migrate_schema


class Database(BaseSqliteDatabase):
    def __init__(self, path: Path):
        super().__init__(path)
        create_or_migrate_schema(self.conn)
