import sqlite3
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


class DrawService:
    def __init__(self, drawing_dir, tool_db_path, jaw_db_path):
        self.drawing_dir = Path(drawing_dir)
        self.tool_db_path = Path(tool_db_path)
        self.jaw_db_path = Path(jaw_db_path)
        self._tool_cache = None
        self._jaw_cache = None
        self._tool_index = None
        self._jaw_index = None

    @staticmethod
    def _open_readonly_connection(db_path):
        db_path = Path(db_path)
        if not db_path.exists():
            return None
        uri = f"file:{db_path.as_posix()}?mode=ro&immutable=1"
        return sqlite3.connect(uri, uri=True)

    @staticmethod
    def _index_refs(refs):
        return {item.get("id", ""): item for item in refs if item.get("id")}

    def get_reference_source_status(self):
        return {
            "tool_db_path": str(self.tool_db_path),
            "tool_db_exists": self.tool_db_path.exists(),
            "jaw_db_path": str(self.jaw_db_path),
            "jaw_db_exists": self.jaw_db_path.exists(),
        }

    def list_drawings(self, search=""):
        if not self.drawing_dir.exists():
            return []
        query = (search or "").strip().lower()
        results = []
        for path in sorted(self.drawing_dir.rglob("*.pdf")):
            drawing_id = path.stem
            if query and query not in drawing_id.lower() and query not in str(path).lower():
                continue
            results.append({"drawing_id": drawing_id, "path": str(path)})
        return results

    def open_drawing(self, drawing_path):
        path = Path(drawing_path)
        if not path.exists():
            return False
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def list_tool_refs(self, force_reload=False, head_filter=None):
        """Return tool id+description pairs, optionally filtered by tool_head ('HEAD1'/'HEAD2')."""
        cache_attr = f"_tool_cache_{head_filter or 'all'}"
        cached = getattr(self, cache_attr, None)
        if cached is not None and not force_reload:
            return list(cached)

        refs = []
        conn = self._open_readonly_connection(self.tool_db_path)
        if conn is None:
            setattr(self, cache_attr, refs)
            if head_filter is None:
                self._tool_cache = refs
            return refs
        conn.row_factory = sqlite3.Row
        try:
            includes_tool_type = True
            if head_filter:
                try:
                    rows = conn.execute(
                        "SELECT id, description, tool_type FROM tools WHERE tool_head = ? COLLATE NOCASE"
                        " ORDER BY id COLLATE NOCASE ASC",
                        (head_filter,),
                    ).fetchall()
                except Exception:
                    # tool_head and/or tool_type may not exist in all DB versions.
                    includes_tool_type = False
                    try:
                        rows = conn.execute(
                            "SELECT id, description FROM tools WHERE tool_head = ? COLLATE NOCASE"
                            " ORDER BY id COLLATE NOCASE ASC",
                            (head_filter,),
                        ).fetchall()
                    except Exception:
                        rows = conn.execute(
                            "SELECT id, description FROM tools ORDER BY id COLLATE NOCASE ASC"
                        ).fetchall()
            else:
                try:
                    rows = conn.execute(
                        "SELECT id, description, tool_type FROM tools ORDER BY id COLLATE NOCASE ASC"
                    ).fetchall()
                except Exception:
                    includes_tool_type = False
                    rows = conn.execute(
                        "SELECT id, description FROM tools ORDER BY id COLLATE NOCASE ASC"
                    ).fetchall()
            for row in rows:
                tool_type = (row["tool_type"] or "").strip() if includes_tool_type else ""
                refs.append(
                    {
                        "id": (row["id"] or "").strip(),
                        "description": (row["description"] or "").strip(),
                        "tool_type": tool_type,
                    }
                )
        finally:
            conn.close()
        setattr(self, cache_attr, refs)
        if head_filter is None:
            self._tool_cache = refs
            self._tool_index = self._index_refs(refs)
        return list(refs)

    def list_jaw_refs(self, force_reload=False):
        if self._jaw_cache is not None and not force_reload:
            return list(self._jaw_cache)

        refs = []
        conn = self._open_readonly_connection(self.jaw_db_path)
        if conn is None:
            self._jaw_cache = refs
            return refs
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT jaw_id, jaw_type, clamping_diameter_text FROM jaws ORDER BY jaw_id COLLATE NOCASE ASC"
            ).fetchall()
            for row in rows:
                jaw_type = (row["jaw_type"] or "").strip()
                details = " ".join(
                    [
                        jaw_type,
                        (row["clamping_diameter_text"] or "").strip(),
                    ]
                ).strip()
                refs.append(
                    {
                        "id": (row["jaw_id"] or "").strip(),
                        "description": details,
                        "jaw_type": jaw_type,
                    }
                )
        finally:
            conn.close()
        self._jaw_cache = refs
        self._jaw_index = self._index_refs(refs)
        return list(refs)

    def get_tool_ref(self, tool_id, force_reload=False):
        tool_id = (tool_id or "").strip()
        if not tool_id:
            return None
        if force_reload or self._tool_index is None:
            self.list_tool_refs(force_reload=force_reload)
        return dict(self._tool_index.get(tool_id, {})) if self._tool_index and tool_id in self._tool_index else None

    def get_jaw_ref(self, jaw_id, force_reload=False):
        jaw_id = (jaw_id or "").strip()
        if not jaw_id:
            return None
        if force_reload or self._jaw_index is None:
            self.list_jaw_refs(force_reload=force_reload)
        return dict(self._jaw_index.get(jaw_id, {})) if self._jaw_index and jaw_id in self._jaw_index else None

    def get_full_jaw(self, jaw_id):
        """Return all columns for a jaw from the jaw database."""
        jaw_id = (jaw_id or "").strip()
        if not jaw_id:
            return None
        conn = self._open_readonly_connection(self.jaw_db_path)
        if conn is None:
            return None
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM jaws WHERE jaw_id = ? COLLATE NOCASE", (jaw_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_full_tool(self, tool_id):
        """Return all columns for a tool from the tool database."""
        tool_id = (tool_id or "").strip()
        if not tool_id:
            return None
        conn = self._open_readonly_connection(self.tool_db_path)
        if conn is None:
            return None
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM tools WHERE id = ? COLLATE NOCASE", (tool_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
