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
        self._tool_uid_index = None
        self._jaw_index = None
        self._tool_db_mtime = None
        self._jaw_db_mtime = None

    @staticmethod
    def _db_mtime(path: Path):
        try:
            return path.stat().st_mtime if Path(path).exists() else None
        except Exception:
            return None

    def _invalidate_tool_cache(self):
        self._tool_cache = None
        self._tool_index = None
        self._tool_uid_index = None
        for attr in list(vars(self).keys()):
            if attr.startswith("_tool_cache_"):
                setattr(self, attr, None)

    def _invalidate_jaw_cache(self):
        self._jaw_cache = None
        self._jaw_index = None

    def _refresh_reference_cache_state(self):
        tool_mtime = self._db_mtime(self.tool_db_path)
        if tool_mtime != self._tool_db_mtime:
            self._tool_db_mtime = tool_mtime
            self._invalidate_tool_cache()

        jaw_mtime = self._db_mtime(self.jaw_db_path)
        if jaw_mtime != self._jaw_db_mtime:
            self._jaw_db_mtime = jaw_mtime
            self._invalidate_jaw_cache()

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
        return self.list_drawings_with_context(search=search, context=None)

    @staticmethod
    def _safe_resolve(path: Path | None) -> Path | None:
        if path is None:
            return None
        try:
            return Path(path).expanduser().resolve()
        except Exception:
            try:
                return Path(path).expanduser()
            except Exception:
                return None

    @staticmethod
    def _clean_text(value) -> str:
        return str(value or "").strip()

    def _context_tokens(self, context: dict | None) -> list[str]:
        payload = dict(context or {})
        tokens = []
        for raw_value in (
            payload.get("work_id"),
            payload.get("drawing_id"),
            payload.get("description"),
        ):
            text = self._clean_text(raw_value)
            if text:
                tokens.append(text.lower())

        drawing_path_text = self._clean_text(payload.get("drawing_path"))
        if drawing_path_text:
            try:
                path = Path(drawing_path_text)
                tokens.append(path.stem.strip().lower())
                tokens.append(path.name.strip().lower())
            except Exception:
                pass

        return [token for token in tokens if token]

    def _context_match_score(self, path: Path, context: dict | None) -> int:
        payload = dict(context or {})
        score = 0
        stem = path.stem.strip().lower()
        name = path.name.strip().lower()
        relative_label = self._drawing_relative_label(path).lower()

        context_path_text = self._clean_text(payload.get("drawing_path"))
        context_path = self._safe_resolve(Path(context_path_text)) if context_path_text else None
        resolved_path = self._safe_resolve(path)
        if context_path is not None and resolved_path is not None:
            if resolved_path == context_path:
                return 100
            if name == context_path.name.strip().lower():
                score = max(score, 94)
            elif stem == context_path.stem.strip().lower():
                score = max(score, 90)

        drawing_id = self._clean_text(payload.get("drawing_id")).lower()
        work_id = self._clean_text(payload.get("work_id")).lower()

        if drawing_id:
            if stem == drawing_id:
                score = max(score, 92)
            elif drawing_id in stem or drawing_id in name or drawing_id in relative_label:
                score = max(score, 80)

        if work_id:
            if stem == work_id:
                score = max(score, 88)
            elif work_id in stem or work_id in name or work_id in relative_label:
                score = max(score, 72)

        for token in self._context_tokens(payload):
            if token and token in relative_label:
                score = max(score, 56)

        return score

    def _drawing_relative_label(self, path: Path) -> str:
        try:
            return path.relative_to(self.drawing_dir).as_posix()
        except Exception:
            return path.name

    def _drawing_category(self, path: Path, linked: bool) -> str:
        if linked:
            return "Linked drawing"
        try:
            relative_parent = path.relative_to(self.drawing_dir).parent
        except Exception:
            return "General"
        if str(relative_parent) in {"", "."}:
            return "General"
        return relative_parent.as_posix()

    def _make_drawing_entry(self, path: Path, context: dict | None, linked: bool = False) -> dict:
        resolved = self._safe_resolve(path) or path
        relative_label = self._drawing_relative_label(resolved)
        category = self._drawing_category(resolved, linked=linked)
        return {
            "drawing_id": resolved.stem,
            "path": str(resolved),
            "name": resolved.name,
            "relative_path": relative_label,
            "category": category,
            "source": "linked" if linked else "library",
            "context_score": self._context_match_score(resolved, context),
        }

    def list_drawings_with_context(self, search="", context=None):
        query = (search or "").strip().lower()
        payload = dict(context or {})
        entries_by_key: dict[str, dict] = {}

        if self.drawing_dir.exists():
            for path in self.drawing_dir.rglob("*.pdf"):
                resolved = self._safe_resolve(path)
                if resolved is None:
                    continue
                key = str(resolved).lower()
                entries_by_key[key] = self._make_drawing_entry(resolved, payload, linked=False)

        explicit_path_text = self._clean_text(payload.get("drawing_path"))
        if explicit_path_text:
            explicit_path = self._safe_resolve(Path(explicit_path_text))
            if explicit_path is not None and explicit_path.exists() and explicit_path.suffix.lower() == ".pdf":
                key = str(explicit_path).lower()
                entries_by_key[key] = self._make_drawing_entry(explicit_path, payload, linked=True)

        results = list(entries_by_key.values())
        if query:
            filtered = []
            for item in results:
                haystacks = (
                    self._clean_text(item.get("drawing_id")).lower(),
                    self._clean_text(item.get("name")).lower(),
                    self._clean_text(item.get("relative_path")).lower(),
                    self._clean_text(item.get("category")).lower(),
                    self._clean_text(item.get("path")).lower(),
                )
                if any(query in haystack for haystack in haystacks):
                    filtered.append(item)
            results = filtered

        results.sort(
            key=lambda item: (
                -int(item.get("context_score") or 0),
                self._clean_text(item.get("category")).lower(),
                self._clean_text(item.get("relative_path")).lower(),
                self._clean_text(item.get("drawing_id")).lower(),
            )
        )
        return results

    def open_drawing(self, drawing_path):
        path = Path(drawing_path)
        if not path.exists():
            return False
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def list_tool_refs(self, force_reload=False, head_filter=None, dedupe_by_id=True):
        """Return tool id+description pairs, optionally filtered by tool_head ('HEAD1'/'HEAD2')."""
        self._refresh_reference_cache_state()
        mode = "dedup" if dedupe_by_id else "raw"
        cache_attr = f"_tool_cache_{head_filter or 'all'}_{mode}"
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
                        "SELECT uid, id, description, tool_type, default_pot FROM tools WHERE tool_head = ? COLLATE NOCASE"
                        " ORDER BY id COLLATE NOCASE ASC, uid DESC",
                        (head_filter,),
                    ).fetchall()
                except Exception:
                    # tool_head and/or tool_type/default_pot may not exist in all DB versions.
                    includes_tool_type = False
                    try:
                        rows = conn.execute(
                            "SELECT uid, id, description FROM tools WHERE tool_head = ? COLLATE NOCASE"
                            " ORDER BY id COLLATE NOCASE ASC",
                            (head_filter,),
                        ).fetchall()
                    except Exception:
                        rows = conn.execute(
                            "SELECT uid, id, description FROM tools ORDER BY id COLLATE NOCASE ASC"
                        ).fetchall()
            else:
                try:
                    rows = conn.execute(
                        "SELECT uid, id, description, tool_type, default_pot FROM tools ORDER BY id COLLATE NOCASE ASC, uid DESC"
                    ).fetchall()
                except Exception:
                    includes_tool_type = False
                    rows = conn.execute(
                        "SELECT uid, id, description FROM tools ORDER BY id COLLATE NOCASE ASC"
                    ).fetchall()
            seen_ids = set()
            for row in rows:
                tool_id = (row["id"] or "").strip()
                if not tool_id:
                    continue
                if dedupe_by_id and tool_id in seen_ids:
                    continue
                seen_ids.add(tool_id)
                tool_type = (row["tool_type"] or "").strip() if includes_tool_type else ""
                default_pot = ""
                if includes_tool_type:
                    try:
                        default_pot = (row["default_pot"] or "").strip()
                    except (IndexError, KeyError):
                        pass
                refs.append(
                    {
                        "uid": row["uid"] if "uid" in row.keys() else None,
                        "id": tool_id,
                        "description": (row["description"] or "").strip(),
                        "tool_type": tool_type,
                        "default_pot": default_pot,
                    }
                )
        finally:
            conn.close()
        setattr(self, cache_attr, refs)
        if head_filter is None:
            self._tool_cache = refs
            self._tool_index = self._index_refs(refs)
            self._tool_uid_index = {
                int(item.get("uid")): item
                for item in refs
                if item.get("uid") is not None
            }
        return list(refs)

    def list_jaw_refs(self, force_reload=False):
        self._refresh_reference_cache_state()
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
        self._refresh_reference_cache_state()
        tool_id = (tool_id or "").strip()
        if not tool_id:
            return None
        if force_reload or self._tool_index is None:
            self.list_tool_refs(force_reload=force_reload)
        return dict(self._tool_index.get(tool_id, {})) if self._tool_index and tool_id in self._tool_index else None

    def get_tool_ref_by_uid(self, tool_uid, force_reload=False):
        self._refresh_reference_cache_state()
        try:
            uid = int(tool_uid)
        except Exception:
            return None
        if force_reload or self._tool_uid_index is None:
            self.list_tool_refs(force_reload=force_reload, dedupe_by_id=False)
        if not self._tool_uid_index:
            return None
        ref = self._tool_uid_index.get(uid)
        return dict(ref) if isinstance(ref, dict) else None

    def get_jaw_ref(self, jaw_id, force_reload=False):
        self._refresh_reference_cache_state()
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
        self._refresh_reference_cache_state()
        tool_id = (tool_id or "").strip()
        if not tool_id:
            return None
        conn = self._open_readonly_connection(self.tool_db_path)
        if conn is None:
            return None
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM tools WHERE id = ? COLLATE NOCASE ORDER BY uid DESC LIMIT 1", (tool_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_full_tool_by_uid(self, tool_uid):
        """Return all columns for a tool row identified by internal UID."""
        self._refresh_reference_cache_state()
        try:
            uid = int(tool_uid)
        except Exception:
            return None
        conn = self._open_readonly_connection(self.tool_db_path)
        if conn is None:
            return None
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM tools WHERE uid = ?", (uid,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
