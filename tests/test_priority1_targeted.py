"""Priority 1 targeted unit tests — pure logic, no running Qt app required.

Covers:
  1. ToolService.list_tools  — search, head filter, type filter
  2. JawService.list_jaws    — spindle-side view_mode filter
  3. Migration idempotence   — create_or_migrate_tools_schema twice, no error
  4. Localization fallback   — missing key, format failure, corrupted JSON
  5. selector_mime           — encode / decode round-trip for tools and jaws
  6. filter_coordinator      — master-filter active/inactive (via light mock page)
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Offscreen Qt platform — must be set before any PySide6 import.
# ---------------------------------------------------------------------------
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# ---------------------------------------------------------------------------
# Ensure the workspace root is on sys.path so app imports resolve.
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
for _candidate in (_WORKSPACE / "Tools and jaws Library", _WORKSPACE):
    candidate_str = str(_candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

# ---------------------------------------------------------------------------
# Create the QApplication singleton early — before any Qt widget import.
# filter_coordinator imports tool_catalog_delegate at module level, which
# imports PySide6.QtWidgets, so Qt must be initialized first.
# ---------------------------------------------------------------------------
from PySide6.QtWidgets import QApplication  # noqa: E402
_APP = QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------------
# Minimal in-memory DB fixture
# ---------------------------------------------------------------------------

class _InMemDb:
    """Minimal stand-in for Database / JawDatabase: exposes .conn only."""

    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def close(self):
        self.conn.close()


# ===========================================================================
# 1. ToolService.list_tools
# ===========================================================================

class TestToolServiceListTools(unittest.TestCase):

    def setUp(self):
        from data.migrations.tools_migrations import create_or_migrate_tools_schema
        from services.tool_service import ToolService

        self._db = _InMemDb()
        create_or_migrate_tools_schema(self._db.conn)
        self.svc = ToolService.__new__(ToolService)
        self.svc.db = self._db

        # Insert test rows directly so we bypass _seed_if_empty side effects.
        rows = [
            ("T001", "HEAD1", "main", "O.D Turning", "Roughing tool", 150.0, 50.0),
            ("T002", "HEAD1", "main", "Drill", "Center drill", 80.0, 20.0),
            ("T003", "HEAD2", "main", "Endmill", "Side mill 10mm", 100.0, 30.0),
        ]
        with self._db.conn:
            for r in rows:
                self._db.conn.execute(
                    "INSERT INTO tools (id, tool_head, spindle_orientation, tool_type, description, geom_x, geom_z) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    r,
                )

    def tearDown(self):
        self._db.close()

    def test_list_all_returns_all(self):
        tools = self.svc.list_tools()
        self.assertEqual(len(tools), 3)

    def test_search_filters_by_description(self):
        tools = self.svc.list_tools(search_text="roughing")
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["id"], "T001")

    def test_search_filters_by_id(self):
        tools = self.svc.list_tools(search_text="T002")
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["id"], "T002")

    def test_type_filter(self):
        tools = self.svc.list_tools(tool_type="Drill")
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["id"], "T002")

    def test_head_filter_head1(self):
        tools = self.svc.list_tools(tool_head="HEAD1")
        ids = {t["id"] for t in tools}
        self.assertIn("T001", ids)
        self.assertIn("T002", ids)
        self.assertNotIn("T003", ids)

    def test_head_filter_head2(self):
        tools = self.svc.list_tools(tool_head="HEAD2")
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["id"], "T003")

    def test_combined_search_and_type(self):
        tools = self.svc.list_tools(search_text="mill", tool_type="Endmill")
        self.assertEqual(len(tools), 1)

    def test_empty_search_returns_all(self):
        tools = self.svc.list_tools(search_text="")
        self.assertEqual(len(tools), 3)

    def test_no_match_returns_empty(self):
        tools = self.svc.list_tools(search_text="zzznomatch")
        self.assertEqual(len(tools), 0)


# ===========================================================================
# 2. JawService.list_jaws — spindle-side view_mode filter
# ===========================================================================

class TestJawServiceListJaws(unittest.TestCase):

    def setUp(self):
        from data.migrations.jaws_migrations import create_or_migrate_jaws_schema
        from services.jaw_service import JawService

        self._db = _InMemDb()
        create_or_migrate_jaws_schema(self._db.conn)
        self.svc = JawService.__new__(JawService)
        self.svc.db = self._db

        rows = [
            ("J001", "Soft jaws", "Main spindle"),
            ("J002", "Hard jaws", "Sub spindle"),
            ("J003", "Soft jaws", "Both"),
        ]
        with self._db.conn:
            for r in rows:
                self._db.conn.execute(
                    "INSERT INTO jaws (jaw_id, jaw_type, spindle_side) VALUES (?, ?, ?)",
                    r,
                )

    def tearDown(self):
        self._db.close()

    def test_view_all_returns_all(self):
        jaws = self.svc.list_jaws(view_mode="all")
        self.assertEqual(len(jaws), 3)

    def test_view_main_excludes_sub_only(self):
        jaws = self.svc.list_jaws(view_mode="main")
        ids = {j["jaw_id"] for j in jaws}
        self.assertIn("J001", ids)   # Main spindle
        self.assertIn("J003", ids)   # Both
        self.assertNotIn("J002", ids)  # Sub spindle only

    def test_view_sub_excludes_main_only(self):
        jaws = self.svc.list_jaws(view_mode="sub")
        ids = {j["jaw_id"] for j in jaws}
        self.assertIn("J002", ids)   # Sub spindle
        self.assertIn("J003", ids)   # Both
        self.assertNotIn("J001", ids)  # Main spindle only

    def test_search_filters_by_jaw_id(self):
        jaws = self.svc.list_jaws(search_text="J001")
        self.assertEqual(len(jaws), 1)
        self.assertEqual(jaws[0]["jaw_id"], "J001")

    def test_type_filter_soft(self):
        jaws = self.svc.list_jaws(jaw_type_filter="Soft jaws")
        ids = {j["jaw_id"] for j in jaws}
        self.assertIn("J001", ids)
        self.assertIn("J003", ids)
        self.assertNotIn("J002", ids)


# ===========================================================================
# 3. Migration idempotence
# ===========================================================================

class TestMigrationIdempotence(unittest.TestCase):

    def test_tools_schema_twice_no_error(self):
        from data.migrations.tools_migrations import create_or_migrate_tools_schema
        with sqlite3.connect(":memory:") as conn:
            create_or_migrate_tools_schema(conn)
            # Running a second time must not raise.
            create_or_migrate_tools_schema(conn)
            cols = {row[1] for row in conn.execute("PRAGMA table_info(tools)").fetchall()}
        self.assertIn("id", cols)
        self.assertIn("tool_type", cols)

    def test_jaws_schema_twice_no_error(self):
        from data.migrations.jaws_migrations import create_or_migrate_jaws_schema
        with sqlite3.connect(":memory:") as conn:
            create_or_migrate_jaws_schema(conn)
            create_or_migrate_jaws_schema(conn)
            cols = {row[1] for row in conn.execute("PRAGMA table_info(jaws)").fetchall()}
        self.assertIn("jaw_id", cols)


# ===========================================================================
# 4. Localization service
# ===========================================================================

class TestLocalizationService(unittest.TestCase):

    def _make_service(self, app_catalog: dict, shared_catalog: dict | None = None,
                      fallback_catalog: dict | None = None) -> "LocalizationService":
        from shared.services.localization_service import LocalizationService

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            app_i18n = workspace / "App" / "i18n"
            shared_i18n = workspace / "shared" / "i18n"
            app_i18n.mkdir(parents=True)
            shared_i18n.mkdir(parents=True)

            (app_i18n / "en.json").write_text(json.dumps(app_catalog), encoding="utf-8")
            if shared_catalog is not None:
                (shared_i18n / "en.json").write_text(json.dumps(shared_catalog), encoding="utf-8")
            if fallback_catalog is not None:
                (app_i18n / "en.json").write_text(json.dumps(fallback_catalog), encoding="utf-8")

            svc = LocalizationService(app_i18n)
            svc.set_language("en")
            return svc

    def test_missing_key_returns_provided_default(self):
        from shared.services.localization_service import LocalizationService

        with tempfile.TemporaryDirectory() as tmp:
            i18n = Path(tmp) / "i18n"
            i18n.mkdir()
            (i18n / "en.json").write_text(json.dumps({"hello": "Hello"}), encoding="utf-8")
            svc = LocalizationService(i18n)
            svc.set_language("en")

            result = svc.t("nonexistent.key", "Fallback text")
            self.assertEqual(result, "Fallback text")

    def test_missing_key_no_default_returns_key(self):
        from shared.services.localization_service import LocalizationService

        with tempfile.TemporaryDirectory() as tmp:
            i18n = Path(tmp) / "i18n"
            i18n.mkdir()
            (i18n / "en.json").write_text(json.dumps({}), encoding="utf-8")
            svc = LocalizationService(i18n)

            result = svc.t("some.missing.key")
            self.assertEqual(result, "some.missing.key")

    def test_format_failure_returns_unformatted_string(self):
        from shared.services.localization_service import LocalizationService

        with tempfile.TemporaryDirectory() as tmp:
            i18n = Path(tmp) / "i18n"
            i18n.mkdir()
            (i18n / "en.json").write_text(
                json.dumps({"msg": "Hello {name}"}), encoding="utf-8"
            )
            svc = LocalizationService(i18n)
            svc.set_language("en")

            # Wrong kwarg — should return the raw template, not raise.
            result = svc.t("msg", wrong_kwarg="x")
            self.assertEqual(result, "Hello {name}")

    def test_corrupted_catalog_does_not_raise(self):
        from shared.services.localization_service import LocalizationService

        with tempfile.TemporaryDirectory() as tmp:
            i18n = Path(tmp) / "i18n"
            i18n.mkdir()
            (i18n / "en.json").write_text("THIS IS NOT JSON }{", encoding="utf-8")
            # Construction must not raise.
            svc = LocalizationService(i18n)
            svc.set_language("en")
            # And t() must still return the default/key.
            self.assertEqual(svc.t("any.key", "default"), "default")

    def test_language_fallback_to_english(self):
        from shared.services.localization_service import LocalizationService

        with tempfile.TemporaryDirectory() as tmp:
            i18n = Path(tmp) / "i18n"
            i18n.mkdir()
            (i18n / "en.json").write_text(json.dumps({"key": "English"}), encoding="utf-8")
            svc = LocalizationService(i18n)
            # Request a language with no catalog → should fall back to "en".
            svc.set_language("fi")
            self.assertEqual(svc.t("key"), "English")


# ===========================================================================
# 5. selector_mime encode / decode round-trip
# ===========================================================================

class TestSelectorMime(unittest.TestCase):
    """selector_mime uses QMimeData which requires a running Qt application."""

    def test_tool_encode_decode_roundtrip(self):
        from PySide6.QtCore import QMimeData
        from ui.selector_mime import (
            SELECTOR_TOOL_MIME,
            decode_tool_payload,
            encode_selector_payload,
        )

        original = [
            {"tool_id": "T001", "tool_uid": 1, "spindle": "main"},
            {"tool_id": "T002", "tool_uid": 2, "spindle": "sub"},
        ]
        mime = QMimeData()
        encode_selector_payload(mime, SELECTOR_TOOL_MIME, original)
        decoded = decode_tool_payload(mime)
        self.assertEqual(decoded, original)

    def test_jaw_encode_decode_roundtrip(self):
        from PySide6.QtCore import QMimeData
        from ui.selector_mime import (
            SELECTOR_JAW_MIME,
            decode_jaw_payload,
            encode_selector_payload,
        )

        original = [{"jaw_id": "J001", "jaw_type": "Soft jaws", "spindle_side": "Main spindle"}]
        mime = QMimeData()
        encode_selector_payload(mime, SELECTOR_JAW_MIME, original)
        decoded = decode_jaw_payload(mime)
        self.assertEqual(decoded, original)

    def test_decode_missing_mime_type_returns_empty(self):
        from PySide6.QtCore import QMimeData
        from ui.selector_mime import decode_tool_payload

        empty_mime = QMimeData()
        self.assertEqual(decode_tool_payload(empty_mime), [])

    def test_decode_corrupt_data_returns_empty(self):
        from PySide6.QtCore import QMimeData
        from ui.selector_mime import SELECTOR_TOOL_MIME, decode_tool_payload

        mime = QMimeData()
        mime.setData(SELECTOR_TOOL_MIME, b"not valid json }{")
        self.assertEqual(decode_tool_payload(mime), [])


# ===========================================================================
# 6. filter_coordinator.apply_filters — master filter active/inactive
# ===========================================================================

class TestFilterCoordinator(unittest.TestCase):
    """Tests apply_filters using a lightweight mock page object."""

    def _make_page(self, tools_in_db: list[dict], *, master_filter_active=False,
                   master_filter_ids: set[str] | None = None,
                   selector_active=False) -> "types.SimpleNamespace":
        """Build a minimal mock page with a real in-memory ToolService."""
        from data.migrations.tools_migrations import create_or_migrate_tools_schema
        from services.tool_service import ToolService

        db = _InMemDb()
        create_or_migrate_tools_schema(db.conn)
        with db.conn:
            for t in tools_in_db:
                db.conn.execute(
                    "INSERT INTO tools (id, tool_head, tool_type, description) VALUES (?, ?, ?, ?)",
                    (t["id"], t.get("tool_head", "HEAD1"), t.get("tool_type", "Drill"), t.get("description", "")),
                )

        svc = ToolService.__new__(ToolService)
        svc.db = db

        page = types.SimpleNamespace(
            tool_service=svc,
            view_mode="home",
            _selector_active=selector_active,
            _master_filter_active=master_filter_active,
            _master_filter_ids=master_filter_ids or set(),
        )
        page._selected_head_filter = lambda: "HEAD1/2"
        page._tool_matches_selector_spindle = lambda tool: True
        return page

    def test_master_filter_inactive_returns_all(self):
        from ui.home_page_support.filter_coordinator import apply_filters

        tools = [
            {"id": "T001", "tool_type": "Drill"},
            {"id": "T002", "tool_type": "Endmill"},
        ]
        page = self._make_page(tools, master_filter_active=False)
        result = apply_filters(page, {})
        self.assertEqual(len(result), 2)

    def test_master_filter_active_restricts_results(self):
        from ui.home_page_support.filter_coordinator import apply_filters

        tools = [
            {"id": "T001", "tool_type": "Drill"},
            {"id": "T002", "tool_type": "Endmill"},
            {"id": "T003", "tool_type": "Reamer"},
        ]
        page = self._make_page(tools, master_filter_active=True, master_filter_ids={"T001", "T003"})
        result = apply_filters(page, {})
        ids = {r["id"] for r in result}
        self.assertIn("T001", ids)
        self.assertIn("T003", ids)
        self.assertNotIn("T002", ids)

    def test_master_filter_empty_set_returns_nothing(self):
        from ui.home_page_support.filter_coordinator import apply_filters

        tools = [{"id": "T001"}, {"id": "T002"}]
        page = self._make_page(tools, master_filter_active=True, master_filter_ids=set())
        result = apply_filters(page, {})
        self.assertEqual(len(result), 0)


# ===========================================================================

if __name__ == "__main__":
    unittest.main()
