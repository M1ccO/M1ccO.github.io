"""JAWS domain schema migrations.

Owns: jaws table creation and all jaws column additions.
Called by the migrations package router.

Extracted from data/migrations.py (Phase 6: Data/Migration Segmentation).
"""

from __future__ import annotations

import sqlite3

from data.migrations.tools_migrations import table_columns

__all__ = [
    "create_or_migrate_jaws_schema",
    "migrate_jaws_schema",
]


def create_or_migrate_jaws_schema(conn: sqlite3.Connection) -> None:
    """Create or upgrade the *jaws* table to the current schema."""
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jaws (
                jaw_id TEXT PRIMARY KEY,
                jaw_type TEXT NOT NULL,
                spindle_side TEXT NOT NULL,
                clamping_diameter_text TEXT DEFAULT '',
                clamping_length TEXT DEFAULT '',
                used_in_work TEXT DEFAULT '',
                turning_washer TEXT DEFAULT '',
                last_modified TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                stl_path TEXT DEFAULT ''
            )
            """
        )

    cols = table_columns(conn, 'jaws')
    additions = {
        'jaw_type': "TEXT NOT NULL DEFAULT 'Soft jaws'",
        'spindle_side': "TEXT NOT NULL DEFAULT 'Main spindle'",
        'clamping_diameter_text': "TEXT DEFAULT ''",
        'clamping_length': "TEXT DEFAULT ''",
        'used_in_work': "TEXT DEFAULT ''",
        'turning_washer': "TEXT DEFAULT ''",
        'last_modified': "TEXT DEFAULT ''",
        'notes': "TEXT DEFAULT ''",
        'stl_path': "TEXT DEFAULT ''",
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
                conn.execute(f'ALTER TABLE jaws ADD COLUMN {name} {ddl}')


# Backward-compatible alias: data/jaw_database.py imports this name directly.
migrate_jaws_schema = create_or_migrate_jaws_schema
