import sqlite3
from pathlib import Path
from .migrations import create_or_migrate_schema


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        create_or_migrate_schema(self.conn)

    def close(self):
        self.conn.close()
