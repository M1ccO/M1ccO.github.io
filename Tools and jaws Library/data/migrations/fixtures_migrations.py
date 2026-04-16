"""FIXTURES domain schema migrations.

Owns: fixtures table creation and all fixtures column additions.
Called by the migrations package router.

Fixtures are the machining-center analogue of jaws.  Each row is either a
``part`` (a standalone clamping element) or an ``assembly`` (composed of
other parts, referenced by ``assembly_part_ids``).
"""

from __future__ import annotations

import sqlite3

from .tools_migrations import table_columns

__all__ = [
    "create_or_migrate_fixtures_schema",
    "migrate_fixtures_schema",
]


def create_or_migrate_fixtures_schema(conn: sqlite3.Connection) -> None:
    """Create or upgrade the *fixtures* table to the current schema."""
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fixtures (
                fixture_id TEXT PRIMARY KEY,
                fixture_kind TEXT NOT NULL DEFAULT 'Part',
                fixture_type TEXT DEFAULT '',
                clamping_diameter_text TEXT DEFAULT '',
                clamping_length TEXT DEFAULT '',
                used_in_work TEXT DEFAULT '',
                turning_washer TEXT DEFAULT '',
                last_modified TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                stl_path TEXT DEFAULT '',
                assembly_part_ids TEXT DEFAULT '[]'
            )
            """
        )

    cols = table_columns(conn, 'fixtures')
    additions = {
        'fixture_kind': "TEXT NOT NULL DEFAULT 'Part'",
        'fixture_type': "TEXT DEFAULT ''",
        'clamping_diameter_text': "TEXT DEFAULT ''",
        'clamping_length': "TEXT DEFAULT ''",
        'used_in_work': "TEXT DEFAULT ''",
        'turning_washer': "TEXT DEFAULT ''",
        'last_modified': "TEXT DEFAULT ''",
        'notes': "TEXT DEFAULT ''",
        'stl_path': "TEXT DEFAULT ''",
        'assembly_part_ids': "TEXT DEFAULT '[]'",
        'preview_plane': "TEXT DEFAULT 'XZ'",
        'preview_rot_x': "INTEGER DEFAULT 0",
        'preview_rot_y': "INTEGER DEFAULT 0",
        'preview_rot_z': "INTEGER DEFAULT 0",
        'measurement_overlays': "TEXT DEFAULT '[]'",
        'preview_selected_part': "INTEGER DEFAULT -1",
        'preview_selected_parts': "TEXT DEFAULT '[]'",
        'preview_transform_mode': "TEXT DEFAULT 'translate'",
        'preview_fine_transform': "INTEGER DEFAULT 0",
    }
    with conn:
        for name, ddl in additions.items():
            if name not in cols:
                conn.execute(f'ALTER TABLE fixtures ADD COLUMN {name} {ddl}')


migrate_fixtures_schema = create_or_migrate_fixtures_schema
