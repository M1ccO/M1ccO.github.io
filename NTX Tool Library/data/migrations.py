import json
import sqlite3


def table_columns(conn: sqlite3.Connection, table_name: str):
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def json_loads(raw):
    if isinstance(raw, list):
        return raw
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


def create_or_migrate_schema(conn: sqlite3.Connection):
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tools (
                id TEXT PRIMARY KEY,
                tool_head TEXT DEFAULT 'HEAD1',
                tool_type TEXT DEFAULT 'Turning',
                description TEXT DEFAULT '',
                geom_x REAL DEFAULT 0,
                geom_z REAL DEFAULT 0,
                radius REAL DEFAULT 0,
                nose_corner_radius REAL DEFAULT 0,
                holder_code TEXT DEFAULT '',
                holder_link TEXT DEFAULT '',
                holder_add_element TEXT DEFAULT '',
                holder_add_element_link TEXT DEFAULT '',
                cutting_type TEXT DEFAULT 'Insert',
                cutting_code TEXT DEFAULT '',
                cutting_link TEXT DEFAULT '',
                cutting_add_element TEXT DEFAULT '',
                cutting_add_element_link TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                drill_nose_angle REAL DEFAULT 0,
                mill_cutting_edges INTEGER DEFAULT 0,
                spare_parts TEXT DEFAULT '',
                geometry_profiles TEXT DEFAULT '[]',
                support_parts TEXT DEFAULT '[]'
            )
            """
        )
    cols = table_columns(conn, 'tools')
    additions = {
        'tool_head': "TEXT DEFAULT 'HEAD1'",
        'tool_type': "TEXT DEFAULT 'Turning'",
        'description': "TEXT DEFAULT ''",
        'geom_x': 'REAL DEFAULT 0',
        'geom_z': 'REAL DEFAULT 0',
        'radius': 'REAL DEFAULT 0',
        'nose_corner_radius': 'REAL DEFAULT 0',
        'holder_code': "TEXT DEFAULT ''",
        'holder_link': "TEXT DEFAULT ''",
        'holder_add_element': "TEXT DEFAULT ''",
        'holder_add_element_link': "TEXT DEFAULT ''",
        'cutting_type': "TEXT DEFAULT 'Insert'",
        'cutting_code': "TEXT DEFAULT ''",
        'cutting_link': "TEXT DEFAULT ''",
        'cutting_add_element': "TEXT DEFAULT ''",
        'cutting_add_element_link': "TEXT DEFAULT ''",
        'notes': "TEXT DEFAULT ''",
        'drill_nose_angle': 'REAL DEFAULT 0',
        'mill_cutting_edges': 'INTEGER DEFAULT 0',
        'spare_parts': "TEXT DEFAULT ''",
        'geometry_profiles': "TEXT DEFAULT '[]'",
        'support_parts': "TEXT DEFAULT '[]'",
        # new column for storing path to an STL file used for 3‑D preview
        'stl_path': "TEXT DEFAULT ''",
    }
    with conn:
        for name, ddl in additions.items():
            if name not in cols:
                conn.execute(f'ALTER TABLE tools ADD COLUMN {name} {ddl}')

    cols = table_columns(conn, 'tools')
    if 'shim_code' in cols or 'screw_code' in cols or 'assembly_parts' in cols:
        migrate_old_part_fields(conn)
    migrate_tool_head_defaults(conn)
    migrate_note_fields(conn)
    migrate_cutting_type(conn)
    migrate_jaws_schema(conn)


def migrate_tool_head_defaults(conn: sqlite3.Connection):
    cols = table_columns(conn, 'tools')
    if 'tool_head' not in cols:
        return
    with conn:
        conn.execute(
            """
            UPDATE tools
            SET tool_head = 'HEAD1'
            WHERE tool_head IS NULL OR trim(tool_head) = ''
            """
        )


def migrate_jaws_schema(conn: sqlite3.Connection):
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
    }
    with conn:
        for name, ddl in additions.items():
            if name not in cols:
                conn.execute(f'ALTER TABLE jaws ADD COLUMN {name} {ddl}')


def migrate_note_fields(conn: sqlite3.Connection):
    cols = table_columns(conn, 'tools')
    if 'notes' not in cols or 'spare_parts' not in cols:
        return
    rows = conn.execute('SELECT id, notes, spare_parts FROM tools').fetchall()
    with conn:
        for row in rows:
            notes = (row['notes'] or '').strip() if hasattr(row, 'keys') else (row[1] or '').strip()
            spare = (row['spare_parts'] or '').strip() if hasattr(row, 'keys') else (row[2] or '').strip()
            if not notes and spare:
                tool_id = row['id'] if hasattr(row, 'keys') else row[0]
                conn.execute('UPDATE tools SET notes = ? WHERE id = ?', (spare, tool_id))


def migrate_cutting_type(conn: sqlite3.Connection):
    cols = table_columns(conn, 'tools')
    if 'cutting_type' not in cols:
        return
    rows = conn.execute('SELECT id, tool_type, cutting_type FROM tools').fetchall()
    with conn:
        for row in rows:
            current = (row['cutting_type'] if hasattr(row, 'keys') else row[2]) or ''
            if current.strip():
                continue
            tool_type = ((row['tool_type'] if hasattr(row, 'keys') else row[1]) or '').strip().lower()
            inferred = 'Insert'
            if tool_type == 'drill':
                inferred = 'Drill'
            elif tool_type == 'mill':
                inferred = 'Mill'
            tool_id = row['id'] if hasattr(row, 'keys') else row[0]
            conn.execute('UPDATE tools SET cutting_type = ? WHERE id = ?', (inferred, tool_id))


def migrate_old_part_fields(conn: sqlite3.Connection):
    rows = conn.execute('SELECT * FROM tools').fetchall()
    with conn:
        for row in rows:
            keys = row.keys()
            current_support = json_loads(row['support_parts'] if 'support_parts' in keys else '[]')
            if current_support:
                continue
            parts = []
            shim = row['shim_code'] if 'shim_code' in keys else ''
            screw = row['screw_code'] if 'screw_code' in keys else ''
            assembly_raw = row['assembly_parts'] if 'assembly_parts' in keys else '[]'
            if shim:
                parts.append({'name': 'Shim', 'code': shim})
            if screw:
                parts.append({'name': 'Screw', 'code': screw})
            for item in json_loads(assembly_raw):
                name = (item.get('name') or '').strip()
                code = (item.get('code') or '').strip()
                if not name or name.lower() in {'holder', 'insert', 'drill', 'mill', 'cutting part'}:
                    continue
                if not any(p['name'].lower() == name.lower() and p['code'] == code for p in parts):
                    parts.append({'name': name, 'code': code})
            conn.execute('UPDATE tools SET support_parts = ? WHERE id = ?', (json.dumps(parts, ensure_ascii=False), row['id']))
