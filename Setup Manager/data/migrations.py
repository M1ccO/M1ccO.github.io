import sqlite3


def table_columns(conn, table_name):
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def _ensure_works_table(conn):
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS works (
                work_id TEXT PRIMARY KEY,
                drawing_id TEXT DEFAULT '',
                description TEXT DEFAULT '',
                drawing_path TEXT DEFAULT '',
                main_jaw_id TEXT DEFAULT '',
                sub_jaw_id TEXT DEFAULT '',
                main_stop_screws TEXT DEFAULT '',
                sub_stop_screws TEXT DEFAULT '',
                head1_zero TEXT DEFAULT '',
                head2_zero TEXT DEFAULT '',
                head1_main_coord TEXT DEFAULT '',
                head1_sub_coord TEXT DEFAULT '',
                head2_main_coord TEXT DEFAULT '',
                head2_sub_coord TEXT DEFAULT '',
                head1_program TEXT DEFAULT '',
                head2_program TEXT DEFAULT '',
                main_program TEXT DEFAULT '',
                head1_sub_program TEXT DEFAULT '',
                head2_sub_program TEXT DEFAULT '',
                head1_main_z TEXT DEFAULT '',
                head1_main_x TEXT DEFAULT '',
                head1_main_y TEXT DEFAULT '',
                head1_main_c TEXT DEFAULT '',
                head1_sub_z TEXT DEFAULT '',
                head1_sub_x TEXT DEFAULT '',
                head1_sub_y TEXT DEFAULT '',
                head1_sub_c TEXT DEFAULT '',
                head2_main_z TEXT DEFAULT '',
                head2_main_x TEXT DEFAULT '',
                head2_main_y TEXT DEFAULT '',
                head2_main_c TEXT DEFAULT '',
                head2_sub_z TEXT DEFAULT '',
                head2_sub_x TEXT DEFAULT '',
                head2_sub_y TEXT DEFAULT '',
                head2_sub_c TEXT DEFAULT '',
                sub_pickup_z TEXT DEFAULT '',
                head1_tool_ids TEXT DEFAULT '[]',
                head2_tool_ids TEXT DEFAULT '[]',
                head1_tool_assignments TEXT DEFAULT '[]',
                head2_tool_assignments TEXT DEFAULT '[]',
                print_pots INTEGER DEFAULT 0,
                robot_info TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT ''
            )
            """
        )

    additions = {
        "drawing_id": "TEXT DEFAULT ''",
        "description": "TEXT DEFAULT ''",
        "drawing_path": "TEXT DEFAULT ''",
        "main_jaw_id": "TEXT DEFAULT ''",
        "sub_jaw_id": "TEXT DEFAULT ''",
        "main_stop_screws": "TEXT DEFAULT ''",
        "sub_stop_screws": "TEXT DEFAULT ''",
        "head1_zero": "TEXT DEFAULT ''",
        "head2_zero": "TEXT DEFAULT ''",
        "head1_main_coord": "TEXT DEFAULT ''",
        "head1_sub_coord": "TEXT DEFAULT ''",
        "head2_main_coord": "TEXT DEFAULT ''",
        "head2_sub_coord": "TEXT DEFAULT ''",
        "head1_program": "TEXT DEFAULT ''",
        "head2_program": "TEXT DEFAULT ''",
        "main_program": "TEXT DEFAULT ''",
        "head1_sub_program": "TEXT DEFAULT ''",
        "head2_sub_program": "TEXT DEFAULT ''",
        "head1_tool_ids": "TEXT DEFAULT '[]'",
        "head2_tool_ids": "TEXT DEFAULT '[]'",
        "robot_info": "TEXT DEFAULT ''",
        "notes": "TEXT DEFAULT ''",
        "created_at": "TEXT DEFAULT ''",
        "updated_at": "TEXT DEFAULT ''",
        "head1_main_z": "TEXT DEFAULT ''",
        "head1_main_x": "TEXT DEFAULT ''",
        "head1_main_y": "TEXT DEFAULT ''",
        "head1_main_c": "TEXT DEFAULT ''",
        "head1_sub_z": "TEXT DEFAULT ''",
        "head1_sub_x": "TEXT DEFAULT ''",
        "head1_sub_y": "TEXT DEFAULT ''",
        "head1_sub_c": "TEXT DEFAULT ''",
        "head2_main_z": "TEXT DEFAULT ''",
        "head2_main_x": "TEXT DEFAULT ''",
        "head2_main_y": "TEXT DEFAULT ''",
        "head2_main_c": "TEXT DEFAULT ''",
        "head2_sub_z": "TEXT DEFAULT ''",
        "head2_sub_x": "TEXT DEFAULT ''",
        "head2_sub_y": "TEXT DEFAULT ''",
        "head2_sub_c": "TEXT DEFAULT ''",
        "sub_pickup_z": "TEXT DEFAULT ''",
        "head1_tool_assignments": "TEXT DEFAULT '[]'",
        "head2_tool_assignments": "TEXT DEFAULT '[]'",
        "print_pots": "INTEGER DEFAULT 0",
    }
    cols = table_columns(conn, "works")
    with conn:
        for name, ddl in additions.items():
            if name not in cols:
                conn.execute(f"ALTER TABLE works ADD COLUMN {name} {ddl}")

        # Backfill the newer program model from legacy head1/head2 program fields.
        conn.execute(
            """
            UPDATE works
            SET
                head1_main_coord = CASE
                    WHEN COALESCE(head1_main_coord, '') <> '' THEN head1_main_coord
                    WHEN COALESCE(head1_zero, '') <> '' THEN head1_zero
                    ELSE head1_main_coord
                END,
                head1_sub_coord = CASE
                    WHEN COALESCE(head1_sub_coord, '') <> '' THEN head1_sub_coord
                    WHEN COALESCE(head1_zero, '') <> '' THEN head1_zero
                    ELSE head1_sub_coord
                END,
                head2_main_coord = CASE
                    WHEN COALESCE(head2_main_coord, '') <> '' THEN head2_main_coord
                    WHEN COALESCE(head2_zero, '') <> '' THEN head2_zero
                    ELSE head2_main_coord
                END,
                head2_sub_coord = CASE
                    WHEN COALESCE(head2_sub_coord, '') <> '' THEN head2_sub_coord
                    WHEN COALESCE(head2_zero, '') <> '' THEN head2_zero
                    ELSE head2_sub_coord
                END,
                main_program = CASE
                    WHEN COALESCE(main_program, '') <> '' THEN main_program
                    WHEN COALESCE(head1_program, '') <> '' AND head1_program = COALESCE(head2_program, '') THEN head1_program
                    WHEN COALESCE(head1_program, '') <> '' AND COALESCE(head2_program, '') = '' THEN head1_program
                    WHEN COALESCE(head2_program, '') <> '' AND COALESCE(head1_program, '') = '' THEN head2_program
                    ELSE main_program
                END,
                head1_sub_program = CASE
                    WHEN COALESCE(head1_sub_program, '') <> '' THEN head1_sub_program
                    WHEN COALESCE(head1_program, '') <> '' AND COALESCE(head2_program, '') <> '' AND head1_program <> head2_program THEN head1_program
                    ELSE head1_sub_program
                END,
                head2_sub_program = CASE
                    WHEN COALESCE(head2_sub_program, '') <> '' THEN head2_sub_program
                    WHEN COALESCE(head1_program, '') <> '' AND COALESCE(head2_program, '') <> '' AND head1_program <> head2_program THEN head2_program
                    ELSE head2_sub_program
                END
            """
        )


def _ensure_logbook_table(conn):
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS logbook (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_id TEXT NOT NULL,
                order_number TEXT DEFAULT '',
                quantity INTEGER DEFAULT 0,
                batch_serial TEXT DEFAULT '',
                date TEXT DEFAULT '',
                notes TEXT DEFAULT ''
            )
            """
        )

    additions = {
        "work_id": "TEXT NOT NULL DEFAULT ''",
        "order_number": "TEXT DEFAULT ''",
        "quantity": "INTEGER DEFAULT 0",
        "batch_serial": "TEXT DEFAULT ''",
        "date": "TEXT DEFAULT ''",
        "notes": "TEXT DEFAULT ''",
    }
    cols = table_columns(conn, "logbook")
    with conn:
        for name, ddl in additions.items():
            if name not in cols:
                conn.execute(f"ALTER TABLE logbook ADD COLUMN {name} {ddl}")


def create_or_migrate_schema(conn):
    if not isinstance(conn, sqlite3.Connection):
        raise TypeError("conn must be sqlite3.Connection")
    _ensure_works_table(conn)
    _ensure_logbook_table(conn)
