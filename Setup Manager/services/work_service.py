import json
import logging
from datetime import datetime


logger = logging.getLogger(__name__)


class WorkService:
    _ZERO_AXES = ("z", "x", "y", "c")
    _ZERO_PREFIXES = ("head1_main", "head1_sub", "head2_main", "head2_sub")
    _SPINDLES = ("main", "sub")

    def __init__(self, database):
        self.db = database

    @staticmethod
    def _parse_json_list(raw_value):
        if isinstance(raw_value, list):
            return [str(item).strip() for item in raw_value if str(item).strip()]
        if not raw_value:
            return []
        if isinstance(raw_value, str):
            text = raw_value.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except Exception:
                logger.debug("Failed to parse JSON list text; falling back to comma split", exc_info=True)
                return [part.strip() for part in text.split(",") if part.strip()]
        return []

    @staticmethod
    def _serialize_json_list(values):
        clean = [str(item).strip() for item in (values or []) if str(item).strip()]
        return json.dumps(clean, ensure_ascii=True)

    @staticmethod
    def _parse_json_object_list(raw_value):
        if isinstance(raw_value, list):
            return [item for item in raw_value if isinstance(item, dict)]
        if not raw_value:
            return []
        if isinstance(raw_value, str):
            text = raw_value.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [item for item in parsed if isinstance(item, dict)]
            except Exception:
                logger.debug("Failed to parse JSON object list", exc_info=True)
        return []

    @staticmethod
    def _serialize_json_object_list(values):
        clean = [item for item in (values or []) if isinstance(item, dict)]
        return json.dumps(clean, ensure_ascii=True)

    @classmethod
    def _normalize_tool_assignment(cls, value, default_spindle="main"):
        if isinstance(value, dict):
            tool_id = str(value.get("tool_id") or value.get("id") or "").strip()
            raw_uid = value.get("tool_uid", value.get("uid"))
            try:
                tool_uid = int(raw_uid) if raw_uid is not None and str(raw_uid).strip() else None
            except Exception:
                logger.debug("Failed to parse tool_uid for assignment normalization", exc_info=True)
                tool_uid = None
            spindle = str(value.get("spindle") or default_spindle or "main").strip().lower()
            comment = str(value.get("comment") or "").strip()
            pot = str(value.get("pot") or "").strip()
            override_id = str(value.get("override_id") or "").strip()
            override_description = str(value.get("override_description") or "").strip()
        else:
            tool_id = str(value or "").strip()
            tool_uid = None
            spindle = str(default_spindle or "main").strip().lower()
            comment = ""
            pot = ""
            override_id = ""
            override_description = ""
        if not tool_id:
            return None
        if spindle not in cls._SPINDLES:
            spindle = "main"
        normalized = {
            "tool_id": tool_id,
            "spindle": spindle,
            "comment": comment,
            "pot": pot,
            "override_id": override_id,
            "override_description": override_description,
        }
        if tool_uid is not None:
            normalized["tool_uid"] = tool_uid
        return normalized

    @classmethod
    def _parse_tool_assignments(cls, raw_value, fallback_ids=None):
        assignments = []
        if isinstance(raw_value, list):
            source = raw_value
        elif isinstance(raw_value, str) and raw_value.strip():
            try:
                parsed = json.loads(raw_value)
            except Exception:
                logger.debug("Failed to parse tool assignments JSON; ignoring malformed payload", exc_info=True)
                parsed = None
            source = parsed if isinstance(parsed, list) else []
        else:
            source = []

        for item in source:
            normalized = cls._normalize_tool_assignment(item)
            if normalized:
                assignments.append(normalized)

        if assignments:
            return assignments

        return [
            normalized
            for normalized in (cls._normalize_tool_assignment(item, "main") for item in (fallback_ids or []))
            if normalized
        ]

    @staticmethod
    def _serialize_tool_assignments(assignments):
        clean = []
        for item in assignments or []:
            normalized = WorkService._normalize_tool_assignment(item)
            if normalized:
                clean.append(normalized)
        return json.dumps(clean, ensure_ascii=True)

    @staticmethod
    def _tool_ids_from_assignments(assignments):
        return [item["tool_id"] for item in (assignments or []) if item.get("tool_id")]

    @staticmethod
    def _normalize_optional_text(value):
        text = (value or "").strip()
        if text in {"-", "--"}:
            return ""
        return text

    def _row_to_work(self, row):
        data = dict(row)
        data["print_pots"] = bool(data.get("print_pots", 0))
        head1_legacy_ids = self._parse_json_list(data.get("head1_tool_ids"))
        head2_legacy_ids = self._parse_json_list(data.get("head2_tool_ids"))
        data["head1_tool_assignments"] = self._parse_tool_assignments(
            data.get("head1_tool_assignments"),
            head1_legacy_ids,
        )
        data["head2_tool_assignments"] = self._parse_tool_assignments(
            data.get("head2_tool_assignments"),
            head2_legacy_ids,
        )
        data["head1_tool_ids"] = self._tool_ids_from_assignments(data["head1_tool_assignments"])
        data["head2_tool_ids"] = self._tool_ids_from_assignments(data["head2_tool_assignments"])
        data["mc_operation_count"] = int(data.get("mc_operation_count") or 0)
        data["mc_operations"] = self._parse_json_object_list(data.get("mc_operations"))
        # Older rows only stored one zero coordinate per head. Keep deriving the
        # per-spindle view from those legacy values so the editor/profile layer
        # can evolve without forcing a schema rewrite.
        data["head1_main_coord"] = (data.get("head1_main_coord") or data.get("head1_zero") or "").strip()
        data["head1_sub_coord"] = (data.get("head1_sub_coord") or data.get("head1_zero") or "").strip()
        data["head2_main_coord"] = (data.get("head2_main_coord") or data.get("head2_zero") or "").strip()
        data["head2_sub_coord"] = (data.get("head2_sub_coord") or data.get("head2_zero") or "").strip()
        data["raw_part_od"] = (data.get("raw_part_od") or "").strip()
        data["raw_part_id"] = (data.get("raw_part_id") or "").strip()
        data["raw_part_length"] = (data.get("raw_part_length") or "").strip()
        for prefix in self._ZERO_PREFIXES:
            for axis in self._ZERO_AXES:
                key = f"{prefix}_{axis}"
                data[key] = (data.get(key) or "").strip()
        if not (data.get("main_program") or "").strip():
            head1_program = (data.get("head1_program") or "").strip()
            head2_program = (data.get("head2_program") or "").strip()
            if head1_program and head1_program == head2_program:
                data["main_program"] = head1_program
            elif head1_program and not head2_program:
                data["main_program"] = head1_program
            elif head2_program and not head1_program:
                data["main_program"] = head2_program
        data["head1_sub_program"] = (data.get("head1_sub_program") or "").strip()
        data["head2_sub_program"] = (data.get("head2_sub_program") or "").strip()
        if not data["head1_sub_program"] or not data["head2_sub_program"]:
            head1_program = (data.get("head1_program") or "").strip()
            head2_program = (data.get("head2_program") or "").strip()
            if head1_program and head2_program and head1_program != head2_program:
                if not data["head1_sub_program"]:
                    data["head1_sub_program"] = head1_program
                if not data["head2_sub_program"]:
                    data["head2_sub_program"] = head2_program
        return data

    def list_works(self, search=""):
        like = f"%{(search or '').strip()}%"
        rows = self.db.conn.execute(
            """
            SELECT *
            FROM works
            WHERE work_id LIKE ?
               OR drawing_id LIKE ?
               OR description LIKE ?
               OR notes LIKE ?
            ORDER BY work_id COLLATE NOCASE ASC
            """,
            (like, like, like, like),
        ).fetchall()
        return [self._row_to_work(row) for row in rows]

    def get_work(self, work_id):
        row = self.db.conn.execute("SELECT * FROM works WHERE work_id = ?", (work_id,)).fetchone()
        return self._row_to_work(row) if row else None

    def save_work(self, work_dict):
        payload = dict(work_dict or {})
        work_id = (payload.get("work_id") or "").strip()
        if not work_id:
            raise ValueError("work_id is required")

        now_iso = datetime.now().isoformat(timespec="seconds")
        existing = self.get_work(work_id)
        created_at = payload.get("created_at") or (existing.get("created_at") if existing else now_iso)

        # The UI may be profile-driven, but persistence stays on the additive
        # legacy schema for compatibility with existing databases and exports.
        row = {
            "work_id": work_id,
            "drawing_id": (payload.get("drawing_id") or "").strip(),
            "description": (payload.get("description") or "").strip(),
            "drawing_path": (payload.get("drawing_path") or "").strip(),
            "raw_part_od": (payload.get("raw_part_od") or "").strip(),
            "raw_part_id": (payload.get("raw_part_id") or "").strip(),
            "raw_part_length": (payload.get("raw_part_length") or "").strip(),
            "main_jaw_id": (payload.get("main_jaw_id") or "").strip(),
            "sub_jaw_id": (payload.get("sub_jaw_id") or "").strip(),
            "main_stop_screws": (payload.get("main_stop_screws") or "").strip(),
            "sub_stop_screws": (payload.get("sub_stop_screws") or "").strip(),
            "head1_zero": (payload.get("head1_zero") or "").strip(),
            "head2_zero": (payload.get("head2_zero") or "").strip(),
            "head1_main_coord": (payload.get("head1_main_coord") or payload.get("head1_zero") or "").strip(),
            "head1_sub_coord": (payload.get("head1_sub_coord") or payload.get("head1_zero") or "").strip(),
            "head2_main_coord": (payload.get("head2_main_coord") or payload.get("head2_zero") or "").strip(),
            "head2_sub_coord": (payload.get("head2_sub_coord") or payload.get("head2_zero") or "").strip(),
            "head1_program": "",
            "head2_program": "",
            "main_program": (payload.get("main_program") or "").strip(),
            "head1_sub_program": (payload.get("head1_sub_program") or "").strip(),
            "head2_sub_program": (payload.get("head2_sub_program") or "").strip(),
            "sub_pickup_z": (payload.get("sub_pickup_z") or "").strip(),
            "head1_tool_assignments": self._serialize_tool_assignments(payload.get("head1_tool_assignments")),
            "head2_tool_assignments": self._serialize_tool_assignments(payload.get("head2_tool_assignments")),
            "head1_tool_ids": self._serialize_json_list(
                self._tool_ids_from_assignments(payload.get("head1_tool_assignments") or [])
            ),
            "head2_tool_ids": self._serialize_json_list(
                self._tool_ids_from_assignments(payload.get("head2_tool_assignments") or [])
            ),
            "mc_operation_count": int(payload.get("mc_operation_count") or 0),
            "mc_operations": self._serialize_json_object_list(payload.get("mc_operations") or []),
            "robot_info": self._normalize_optional_text(payload.get("robot_info")),
            "notes": self._normalize_optional_text(payload.get("notes")),
            "print_pots": 1 if payload.get("print_pots") else 0,
            "created_at": created_at,
            "updated_at": now_iso,
        }
        for prefix in self._ZERO_PREFIXES:
            for axis in self._ZERO_AXES:
                key = f"{prefix}_{axis}"
                row[key] = (payload.get(key) or "").strip()

        columns = list(row.keys())
        placeholders = ", ".join(["?"] * len(columns))
        update_clause = ", ".join([f"{col}=excluded.{col}" for col in columns if col != "work_id"])

        with self.db.conn:
            self.db.conn.execute(
                f"""
                INSERT INTO works ({', '.join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(work_id) DO UPDATE SET {update_clause}
                """,
                [row[col] for col in columns],
            )
        return self.get_work(work_id)

    def delete_work(self, work_id):
        with self.db.conn:
            self.db.conn.execute("DELETE FROM works WHERE work_id = ?", (work_id,))

    def duplicate_work(self, source_id, new_id, new_description=""):
        source = self.get_work(source_id)
        if not source:
            raise ValueError(f"source work '{source_id}' does not exist")
        if self.get_work(new_id):
            raise ValueError(f"work '{new_id}' already exists")

        clone = dict(source)
        clone["work_id"] = (new_id or "").strip()
        clone["description"] = (new_description or source.get("description") or "").strip()
        clone["created_at"] = None
        clone["updated_at"] = None
        return self.save_work(clone)

    # ------------------------------------------------------------------
    # app_config — database-bound key/value store
    # ------------------------------------------------------------------

    def get_config_value(self, key: str, default: str = "") -> str:
        """Return a value from the app_config table, or *default* if not found."""
        try:
            row = self.db.conn.execute(
                "SELECT value FROM app_config WHERE key = ?", (str(key),)
            ).fetchone()
            if row is None:
                return default
            return str(row[0] if row[0] is not None else default)
        except Exception:
            logger.debug("get_config_value failed for key=%r", key, exc_info=True)
            return default

    def set_config_value(self, key: str, value: str) -> None:
        """Upsert a value in the app_config table."""
        try:
            with self.db.conn:
                self.db.conn.execute(
                    "INSERT INTO app_config (key, value) VALUES (?, ?)"
                    " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (str(key), str(value or "")),
                )
        except Exception:
            logger.debug("set_config_value failed for key=%r", key, exc_info=True)

    def get_machine_profile_key(self) -> str:
        """Return the machine profile key bound to this database.

        Returns an empty string when the database is fresh and no profile
        has been configured yet (the bootstrap wizard should be shown).
        Returns ``'ntx_2sp_2h'`` as the safe default for upgraded existing
        databases (backfilled by the migration).
        """
        return self.get_config_value("machine_profile_key", "")

    def set_machine_profile_key(self, key: str) -> None:
        """Bind a machine profile key to this database.

        This is the authoritative write path.  Callers should also mirror
        the value to ``shared_ui_preferences.json`` via
        ``UiPreferencesService.set_machine_profile_key`` so both apps stay
        in sync without cross-app imports.
        """
        from machine_profiles import DEFAULT_PROFILE_KEY, PROFILE_REGISTRY
        normalized = str(key or "").strip().lower()
        if not normalized or normalized not in PROFILE_REGISTRY:
            normalized = DEFAULT_PROFILE_KEY
        self.set_config_value("machine_profile_key", normalized)
