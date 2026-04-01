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
                support_parts TEXT DEFAULT '[]',
                component_items TEXT DEFAULT '[]',
                measurement_overlays TEXT DEFAULT '[]'
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
        'component_items': "TEXT DEFAULT '[]'",
        'measurement_overlays': "TEXT DEFAULT '[]'",
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
    migrate_tools_uid_schema(conn)
    migrate_default_pot(conn)
    migrate_component_items(conn)
    migrate_jaws_schema(conn)


def migrate_default_pot(conn: sqlite3.Connection):
    cols = table_columns(conn, 'tools')
    if 'default_pot' not in cols:
        with conn:
            conn.execute("ALTER TABLE tools ADD COLUMN default_pot TEXT DEFAULT ''")


def migrate_tools_uid_schema(conn: sqlite3.Connection):
    cols = table_columns(conn, 'tools')
    if 'uid' in cols:
        with conn:
            conn.execute('CREATE INDEX IF NOT EXISTS idx_tools_id ON tools(id)')
        return

    has_measurement_overlays = 'measurement_overlays' in cols

    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tools_new (
                uid INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT NOT NULL,
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
                support_parts TEXT DEFAULT '[]',
                component_items TEXT DEFAULT '[]',
                measurement_overlays TEXT DEFAULT '[]',
                stl_path TEXT DEFAULT '',
                default_pot TEXT DEFAULT ''
            )
            """
        )
        insert_sql = (
            """
            INSERT INTO tools_new (
                id, tool_head, tool_type, description, geom_x, geom_z, radius,
                nose_corner_radius, holder_code, holder_link, holder_add_element, holder_add_element_link,
                cutting_type, cutting_code, cutting_link, cutting_add_element, cutting_add_element_link,
                notes, drill_nose_angle, mill_cutting_edges, spare_parts,
                geometry_profiles, support_parts, component_items, measurement_overlays, stl_path
            )
            SELECT
                id, tool_head, tool_type, description, geom_x, geom_z, radius,
                nose_corner_radius, holder_code, holder_link, holder_add_element, holder_add_element_link,
                cutting_type, cutting_code, cutting_link, cutting_add_element, cutting_add_element_link,
                notes, drill_nose_angle, mill_cutting_edges, spare_parts,
                geometry_profiles, support_parts, component_items, {measurement_overlays}, stl_path
            FROM tools
            """
        ).format(
            measurement_overlays='measurement_overlays' if has_measurement_overlays else "'[]'"
        )
        conn.execute(insert_sql)
        conn.execute('DROP TABLE tools')
        conn.execute('ALTER TABLE tools_new RENAME TO tools')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_tools_id ON tools(id)')


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


def _legacy_component_items_from_row(row):
    keys = row.keys() if hasattr(row, 'keys') else []
    components = []

    def _add(role: str, label: str, code: str, link: str = '', group: str = ''):
        code_text = (code or '').strip()
        if not code_text:
            return
        components.append(
            {
                'role': role,
                'label': label,
                'code': code_text,
                'link': (link or '').strip(),
                'group': (group or '').strip(),
                'order': len(components),
            }
        )

    holder_code = row['holder_code'] if 'holder_code' in keys else ''
    holder_link = row['holder_link'] if 'holder_link' in keys else ''
    holder_add = row['holder_add_element'] if 'holder_add_element' in keys else ''
    holder_add_link = row['holder_add_element_link'] if 'holder_add_element_link' in keys else ''
    cutting_type = (row['cutting_type'] if 'cutting_type' in keys else 'Insert') or 'Insert'
    cutting_code = row['cutting_code'] if 'cutting_code' in keys else ''
    cutting_link = row['cutting_link'] if 'cutting_link' in keys else ''
    cutting_add = row['cutting_add_element'] if 'cutting_add_element' in keys else ''
    cutting_add_link = row['cutting_add_element_link'] if 'cutting_add_element_link' in keys else ''

    _add('holder', 'Holder', holder_code, holder_link)
    _add('holder', 'Add. Element', holder_add, holder_add_link)
    _add('cutting', str(cutting_type).strip() or 'Insert', cutting_code, cutting_link)
    _add('cutting', f"Add. {str(cutting_type).strip() or 'Insert'}", cutting_add, cutting_add_link)

    support_parts = json_loads(row['support_parts'] if 'support_parts' in keys else '[]')
    if isinstance(support_parts, list):
        for part in support_parts:
            if isinstance(part, str):
                try:
                    part = json.loads(part)
                except Exception:
                    part = {'name': part, 'code': '', 'link': '', 'group': ''}
            if not isinstance(part, dict):
                continue
            _add(
                'support',
                (part.get('name') or 'Part').strip() or 'Part',
                part.get('code', ''),
                part.get('link', ''),
                part.get('group', ''),
            )

    return components


def migrate_component_items(conn: sqlite3.Connection):
    cols = table_columns(conn, 'tools')
    if 'component_items' not in cols:
        return

    rows = conn.execute('SELECT uid, * FROM tools').fetchall()
    with conn:
        for row in rows:
            raw = row['component_items'] if 'component_items' in row.keys() else ''
            current = json_loads(raw)
            if isinstance(current, list) and current:
                continue
            components = _legacy_component_items_from_row(row)
            uid = row['uid'] if 'uid' in row.keys() else None
            if uid is None:
                conn.execute(
                    'UPDATE tools SET component_items = ? WHERE id = ?',
                    (json.dumps(components, ensure_ascii=False), row['id']),
                )
            else:
                conn.execute(
                    'UPDATE tools SET component_items = ? WHERE uid = ?',
                    (json.dumps(components, ensure_ascii=False), uid),
                )


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
