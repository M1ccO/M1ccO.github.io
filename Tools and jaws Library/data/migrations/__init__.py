"""Migration package for Tools and Jaws Library.

Segments schema migration ownership by domain (Phase 6).
All existing imports of ``data.migrations`` continue to work unchanged —
this package is a drop-in replacement for the old ``data/migrations.py``
module at the same import path.

Public API (unchanged from pre-Phase-6):
    create_or_migrate_schema(conn)   — combined entry point (tools + jaws)
    migrate_jaws_schema(conn)        — jaws-only entry point (jaw_database.py)
    table_columns(conn, table_name)  — column-set helper
    json_loads(raw)                  — safe JSON list parser

New domain-scoped entry points (Phase 6+):
    create_or_migrate_tools_schema(conn)
    create_or_migrate_jaws_schema(conn)
"""

from __future__ import annotations

import sqlite3

from .fixtures_migrations import (
    create_or_migrate_fixtures_schema,
    migrate_fixtures_schema,
)
from .jaws_migrations import (
    create_or_migrate_jaws_schema,
    migrate_jaws_schema,
)
from .tools_migrations import (
    create_or_migrate_tools_schema,
    json_loads,
    table_columns,
)

__all__ = [
    "create_or_migrate_fixtures_schema",
    "create_or_migrate_jaws_schema",
    "create_or_migrate_schema",
    "create_or_migrate_tools_schema",
    "json_loads",
    "migrate_fixtures_schema",
    "migrate_jaws_schema",
    "table_columns",
]


def create_or_migrate_schema(conn: sqlite3.Connection) -> None:
    """Combined entry point: run tools migrations then jaws migrations."""
    create_or_migrate_tools_schema(conn)
    create_or_migrate_jaws_schema(conn)
