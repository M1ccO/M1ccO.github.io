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
import importlib.util
from pathlib import Path
from unittest import mock

# ---------------------------------------------------------------------------
# Offscreen Qt platform — must be set before any PySide6 import.
# ---------------------------------------------------------------------------
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# ---------------------------------------------------------------------------
# Ensure the workspace root is on sys.path so app imports resolve.
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
_SETUP_MANAGER_ROOT = _WORKSPACE / "Setup Manager"
_TOOLS_LIBRARY_ROOT = _WORKSPACE / "Tools and jaws Library"
for _candidate in (_WORKSPACE / "Tools and jaws Library", _WORKSPACE):
    candidate_str = str(_candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)


def _prefer_tools_library_namespace() -> None:
    """Ensure Tool Library packages win for ambiguous top-level imports.

    The monorepo has two apps with same top-level package names (ui/data/services/config).
    When unittest discovery imports modules in different order, Setup Manager modules can
    shadow Tool Library modules and break these tests.
    """
    tools_root = str(_TOOLS_LIBRARY_ROOT)
    setup_root = str(_SETUP_MANAGER_ROOT)

    if tools_root in sys.path:
        sys.path.remove(tools_root)
    sys.path.insert(0, tools_root)

    prefixed_roots = ("ui", "data", "services", "models")
    for mod_name in list(sys.modules.keys()):
        if mod_name == "config" or mod_name.startswith(tuple(f"{root}." for root in prefixed_roots)) or mod_name in prefixed_roots:
            mod = sys.modules.get(mod_name)
            mod_file = str(getattr(mod, "__file__", "") or "")
            if setup_root and setup_root in mod_file:
                sys.modules.pop(mod_name, None)


_prefer_tools_library_namespace()


def _load_module_from_path(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module {module_name} from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SETUP_MIGRATIONS = _load_module_from_path(
    "setup_manager_migrations_for_tests",
    _SETUP_MANAGER_ROOT / "data" / "migrations.py",
)
_SETUP_WORK_SERVICE = _load_module_from_path(
    "setup_manager_work_service_for_tests",
    _SETUP_MANAGER_ROOT / "services" / "work_service.py",
)
_SETUP_LOGBOOK_SERVICE = _load_module_from_path(
    "setup_manager_logbook_service_for_tests",
    _SETUP_MANAGER_ROOT / "services" / "logbook_service.py",
)
_SETUP_DRAW_SERVICE = _load_module_from_path(
    "setup_manager_draw_service_for_tests",
    _SETUP_MANAGER_ROOT / "services" / "draw_service.py",
)
_SETUP_SETUP_CARD_POLICY = _load_module_from_path(
    "setup_manager_setup_card_policy_for_tests",
    _SETUP_MANAGER_ROOT / "services" / "setup_card_policy.py",
)


def _load_tool_library_main_window_module():
    _prefer_tools_library_namespace()
    return _load_module_from_path(
        "tool_library_main_window_for_tests",
        _WORKSPACE / "Tools and jaws Library" / "ui" / "main_window.py",
    )


def _load_setup_manager_print_service_module():
    setup_root_str = str(_SETUP_MANAGER_ROOT)
    original_config = sys.modules.pop("config", None)
    sys.path.insert(0, setup_root_str)
    try:
        return _load_module_from_path(
            "setup_manager_print_service_for_tests",
            _SETUP_MANAGER_ROOT / "services" / "print_service.py",
        )
    finally:
        try:
            sys.path.remove(setup_root_str)
        except ValueError:
            pass
        if original_config is not None:
            sys.modules["config"] = original_config
        else:
            sys.modules.pop("config", None)


_SETUP_PRINT_SERVICE = _load_setup_manager_print_service_module()

# ---------------------------------------------------------------------------
# Create the QApplication singleton early — before any Qt widget import.
# filter_coordinator imports tool_catalog_delegate at module level, which
# imports PySide6.QtWidgets, so Qt must be initialized first.
# ---------------------------------------------------------------------------
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QListWidget, QVBoxLayout, QWidget  # noqa: E402
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

    def setUp(self):
        _prefer_tools_library_namespace()
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
# 7. WorkService business logic
# ===========================================================================

class TestWorkService(unittest.TestCase):

    def setUp(self):
        self._db = _InMemDb()
        _SETUP_MIGRATIONS.create_or_migrate_schema(self._db.conn)

        WorkService = _SETUP_WORK_SERVICE.WorkService
        self.svc = WorkService.__new__(WorkService)
        self.svc.db = self._db

    def tearDown(self):
        self._db.close()

    def test_save_work_requires_work_id(self):
        with self.assertRaises(ValueError):
            self.svc.save_work({"work_id": ""})

    def test_save_and_get_work_roundtrip_assignments_and_flags(self):
        saved = self.svc.save_work(
            {
                "work_id": "W001",
                "drawing_id": "D-100",
                "description": "Primary setup",
                "head1_tool_assignments": [
                    {
                        "tool_id": "T001",
                        "tool_uid": "12",
                        "spindle": "MAIN",
                        "comment": "roughing",
                        "pot": "P01",
                    },
                    {
                        "tool_id": "T002",
                        "spindle": "invalid-spindle",
                    },
                ],
                "head2_tool_assignments": [{"tool_id": "T010", "spindle": "sub"}],
                "print_pots": True,
                "notes": "--",
                "robot_info": "-",
            }
        )

        self.assertEqual(saved["work_id"], "W001")
        self.assertEqual(saved["head1_tool_ids"], ["T001", "T002"])
        self.assertEqual(saved["head2_tool_ids"], ["T010"])
        self.assertEqual(saved["head1_tool_assignments"][0]["tool_uid"], 12)
        self.assertEqual(saved["head1_tool_assignments"][1]["spindle"], "main")
        self.assertTrue(saved["print_pots"])
        self.assertEqual(saved["notes"], "")
        self.assertEqual(saved["robot_info"], "")

    def test_legacy_tool_ids_fallback_when_assignments_missing(self):
        with self._db.conn:
            self._db.conn.execute(
                "INSERT INTO works (work_id, head1_tool_ids, head1_tool_assignments) VALUES (?, ?, ?)",
                ("W-LEGACY", "[\"T100\", \"T101\"]", ""),
            )

        work = self.svc.get_work("W-LEGACY")
        self.assertEqual(work["head1_tool_ids"], ["T100", "T101"])
        self.assertEqual(
            [item["tool_id"] for item in work["head1_tool_assignments"]],
            ["T100", "T101"],
        )

    def test_row_to_work_derives_program_fields_from_legacy_columns(self):
        with self._db.conn:
            self._db.conn.execute(
                "INSERT INTO works (work_id, head1_program, head2_program, main_program, head1_sub_program, head2_sub_program) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("W-PROG", "O100", "O200", "", "", ""),
            )

        work = self.svc.get_work("W-PROG")
        self.assertEqual(work["main_program"], "")
        self.assertEqual(work["head1_sub_program"], "O100")
        self.assertEqual(work["head2_sub_program"], "O200")

    def test_duplicate_work_creates_new_record_with_override_description(self):
        self.svc.save_work(
            {
                "work_id": "W-SRC",
                "description": "Original",
                "head1_tool_assignments": [{"tool_id": "T001", "spindle": "main"}],
            }
        )

        clone = self.svc.duplicate_work("W-SRC", "W-CLONE", "Cloned setup")
        self.assertEqual(clone["work_id"], "W-CLONE")
        self.assertEqual(clone["description"], "Cloned setup")
        self.assertEqual(clone["head1_tool_ids"], ["T001"])

    def test_delete_work_removes_row(self):
        self.svc.save_work({"work_id": "W-DEL", "description": "to delete"})
        self.assertIsNotNone(self.svc.get_work("W-DEL"))

        self.svc.delete_work("W-DEL")
        self.assertIsNone(self.svc.get_work("W-DEL"))

    def test_list_works_search_filters_by_description(self):
        self.svc.save_work({"work_id": "W-A", "description": "Alpha rough"})
        self.svc.save_work({"work_id": "W-B", "description": "Beta finish"})

        results = self.svc.list_works(search="rough")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["work_id"], "W-A")


# ===========================================================================
# 8. PrintService helper behavior
# ===========================================================================

class TestPrintServiceHelpers(unittest.TestCase):

    def setUp(self):
        PrintService = _SETUP_PRINT_SERVICE.PrintService
        self.svc = PrintService()

    def test_coord_z_combines_coord_and_z(self):
        self.assertEqual(self.svc._coord_z("A", "Z10"), "A | Z10")
        self.assertEqual(self.svc._coord_z("", "Z10"), "Z10")
        self.assertEqual(self.svc._coord_z("A", ""), "A")
        self.assertEqual(self.svc._coord_z("", ""), "-")

    def test_tool_entry_normalizes_spindle_and_applies_overrides(self):
        tool = self.svc._tool_entry_data(
            {
                "tool_id": "T001",
                "spindle": "INVALID",
                "override_id": "T999",
                "override_description": "Override",
            }
        )
        self.assertIsNotNone(tool)
        self.assertEqual(tool["spindle"], "main")
        self.assertEqual(tool["id"], "T999")
        self.assertEqual(tool["description"], "Override")

    def test_tool_entry_unknown_tool_returns_minimal_payload(self):
        tool = self.svc._tool_entry_data({"tool_id": "T404", "spindle": "sub"})
        self.assertEqual(tool["id"], "T404")
        self.assertEqual(tool["description"], "")
        self.assertEqual(tool["spindle"], "sub")

    def test_get_logbook_color_invalid_date_uses_fallback(self):
        color = self.svc._get_logbook_color_for_date("not-a-date")
        self.assertEqual(color, self.svc._hex_to_rgb("#8B8B8B"))

    def test_setup_card_policy_builds_machining_center_sections(self):
        profile = _SETUP_SETUP_CARD_POLICY.resolve_setup_card_profile("machining_center_3ax")
        sections = _SETUP_SETUP_CARD_POLICY.build_setup_card_sections(
            self.svc,
            {
                "main_program": "O300",
                "mc_operations": [
                    {
                        "op_key": "OP10",
                        "coord": "G54",
                        "sub_program": "O301",
                        "fixture_ids": ["FIX-01"],
                        "selected_fixture_part": "PART-01",
                        "axes": {"x": "0", "y": "0", "z": "120"},
                    }
                ],
            },
            profile,
        )
        titles = [section["title"] for section in sections]
        self.assertIn("Operations", titles)
        self.assertIn("Fixtures", titles)


class TestPrintServicePdfGuards(unittest.TestCase):

    def setUp(self):
        PrintService = _SETUP_PRINT_SERVICE.PrintService
        self.svc = PrintService()
        self._real_import = __import__

    def _missing_reportlab_import(self, name, globals=None, locals=None, fromlist=(), level=0):
        if name == "reportlab" or name.startswith("reportlab."):
            raise ImportError("reportlab not available")
        return self._real_import(name, globals, locals, fromlist, level)

    def test_generate_setup_card_requires_reportlab(self):
        with mock.patch("builtins.__import__", side_effect=self._missing_reportlab_import):
            with self.assertRaisesRegex(RuntimeError, "reportlab is required for PDF generation"):
                self.svc.generate_setup_card({}, None, Path("ignored.pdf"))

    def test_generate_logbook_entry_card_requires_reportlab(self):
        with mock.patch("builtins.__import__", side_effect=self._missing_reportlab_import):
            with self.assertRaisesRegex(RuntimeError, "reportlab is required for PDF generation"):
                self.svc.generate_logbook_entry_card({}, {}, Path("ignored.pdf"))


@unittest.skipUnless(importlib.util.find_spec("reportlab"), "reportlab not installed")
class TestPrintServicePdfSmoke(unittest.TestCase):

    def setUp(self):
        PrintService = _SETUP_PRINT_SERVICE.PrintService
        self.svc = PrintService()

    def test_generate_setup_card_writes_pdf_file(self):
        work = {
            "work_id": "W-PDF-1",
            "drawing_id": "D-100",
            "description": "PDF setup smoke",
            "main_program": "O100",
            "head1_sub_program": "",
            "head2_sub_program": "",
            "main_jaw_id": "",
            "sub_jaw_id": "",
            "head1_tool_assignments": [{"tool_id": "T001", "spindle": "main"}],
            "head2_tool_assignments": [{"tool_id": "T002", "spindle": "sub"}],
            "print_pots": False,
            "notes": "",
            "robot_info": "",
        }

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "setup_card.pdf"
            result = self.svc.generate_setup_card(work, None, output_path)
            self.assertEqual(Path(result), output_path)
            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 0)

    def test_generate_dispatch_card_writes_pdf_file(self):
        work = {
            "work_id": "W-PDF-2",
            "drawing_id": "D-200",
            "description": "Dispatch smoke",
            "main_jaw_id": "",
            "sub_jaw_id": "",
            "main_program": "O200",
            "head1_sub_program": "",
            "head2_sub_program": "",
            "main_stop_screws": "",
            "sub_stop_screws": "",
        }
        entry = {
            "batch_serial": "A26",
            "order_number": "500",
            "quantity": 2,
            "date": "2026-04-14",
        }

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "dispatch_card.pdf"
            result = self.svc.generate_dispatch_card(work, entry, output_path)
            self.assertEqual(Path(result), output_path)
            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 0)

    def test_generate_logbook_entry_card_writes_pdf_file(self):
        work = {"work_id": "W-PDF-3"}
        entry = {
            "work_id": "W-PDF-3",
            "order_number": "700",
            "date": "2026-04-14",
            "batch_serial": "C26",
            "quantity": 5,
            "notes": "Smoke test entry",
        }

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "logbook_entry.pdf"
            result = self.svc.generate_logbook_entry_card(work, entry, output_path)
            self.assertEqual(Path(result), output_path)
            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 0)


class TestLogbookService(unittest.TestCase):

    def setUp(self):
        self._db = _InMemDb()
        _SETUP_MIGRATIONS.create_or_migrate_schema(self._db.conn)

        LogbookService = _SETUP_LOGBOOK_SERVICE.LogbookService
        self.svc = LogbookService(self._db)

    def tearDown(self):
        self._db.close()

    def test_generate_next_serial_advances_past_existing_prefixes(self):
        with self._db.conn:
            self._db.conn.execute(
                "INSERT INTO logbook (work_id, batch_serial, date) VALUES (?, ?, ?)",
                ("W001", "A26", "2026-04-01"),
            )
            self._db.conn.execute(
                "INSERT INTO logbook (work_id, batch_serial, date) VALUES (?, ?, ?)",
                ("W001", "B26/4", "2026-04-02"),
            )

        self.assertEqual(self.svc.generate_next_serial("W001", 2026), "C26")

    def test_latest_entries_by_work_ids_returns_latest_per_work(self):
        with self._db.conn:
            self._db.conn.execute(
                "INSERT INTO logbook (work_id, order_number, quantity, batch_serial, date, notes) VALUES (?, ?, ?, ?, ?, ?)",
                ("W001", "10", 1, "A26", "2026-04-01", "older"),
            )
            self._db.conn.execute(
                "INSERT INTO logbook (work_id, order_number, quantity, batch_serial, date, notes) VALUES (?, ?, ?, ?, ?, ?)",
                ("W001", "11", 2, "B26", "2026-04-03", "newer"),
            )
            self._db.conn.execute(
                "INSERT INTO logbook (work_id, order_number, quantity, batch_serial, date, notes) VALUES (?, ?, ?, ?, ?, ?)",
                ("W002", "20", 3, "A26", "2026-04-02", "other"),
            )

        latest = self.svc.latest_entries_by_work_ids(["W001", "W002"])
        self.assertEqual(latest["W001"]["notes"], "newer")
        self.assertEqual(latest["W002"]["order_number"], "20")

    def test_format_date_dmy_invalid_returns_original_text(self):
        self.assertEqual(self.svc._format_date_dmy("not-a-date"), "not-a-date")


class TestDrawService(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._drawing_dir = Path(self._tmp.name) / "drawings"
        self._drawing_dir.mkdir()
        (self._drawing_dir / "alpha.pdf").write_text("", encoding="utf-8")
        subdir = self._drawing_dir / "subfolder"
        subdir.mkdir()
        (subdir / "beta.pdf").write_text("", encoding="utf-8")
        self._external_pdf = Path(self._tmp.name) / "linked.pdf"
        self._external_pdf.write_text("", encoding="utf-8")

        DrawService = _SETUP_DRAW_SERVICE.DrawService
        self.svc = DrawService(
            self._drawing_dir,
            Path(self._tmp.name) / "tools.db",
            Path(self._tmp.name) / "jaws.db",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_list_drawings_with_context_prioritizes_explicit_linked_path(self):
        results = self.svc.list_drawings_with_context(
            context={"drawing_path": str(self._external_pdf)}
        )

        self.assertGreaterEqual(len(results), 3)
        self.assertEqual(results[0]["source"], "linked")
        self.assertEqual(results[0]["context_score"], 100)
        self.assertEqual(Path(results[0]["path"]), self._external_pdf.resolve())

    def test_list_drawings_search_matches_relative_path_and_category(self):
        results = self.svc.list_drawings_with_context(search="subfolder")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["drawing_id"], "beta")
        self.assertEqual(results[0]["category"], "subfolder")


class TestDetailPanelBuilders(unittest.TestCase):

    def setUp(self):
        _prefer_tools_library_namespace()

    def test_normalized_component_items_filters_invalid_entries_and_sorts_order(self):
        from ui.home_page_support.detail_panel_builder import DetailPanelBuilder

        builder = DetailPanelBuilder(types.SimpleNamespace())
        normalized = builder._normalized_component_items(
            {
                "component_items": json.dumps(
                    [
                        {"role": "support", "code": "S-10", "label": " Support ", "order": "bad"},
                        {"role": "holder", "code": "H-20", "label": "Holder", "order": 2},
                        {"role": "junk", "code": "X-00", "order": 1},
                        {"role": "cutting", "label": "Missing code"},
                    ]
                )
            }
        )

        self.assertEqual([item["code"] for item in normalized], ["S-10", "H-20"])
        self.assertEqual(normalized[0]["label"], "Support")
        self.assertEqual(normalized[0]["order"], 0)
        self.assertEqual(normalized[1]["order"], 2)

    def test_spare_index_by_component_accepts_dict_and_json_items(self):
        from ui.home_page_support.detail_panel_builder import DetailPanelBuilder

        index = DetailPanelBuilder._spare_index_by_component(
            [
                json.dumps({"component_code": "H-20", "name": "Shim"}),
                {"component": "S-10", "name": "Clamp"},
                "not-json",
            ]
        )

        self.assertIn("H-20", index)
        self.assertIn("S-10", index)
        self.assertEqual(index["H-20"][0]["name"], "Shim")
        self.assertEqual(index["S-10"][0]["name"], "Clamp")


class TestJawPreviewRules(unittest.TestCase):

    def setUp(self):
        _prefer_tools_library_namespace()

    def test_parts_payload_parses_json_list_and_filters_non_dict_items(self):
        from ui.jaw_page_support.preview_rules import jaw_preview_parts_payload

        payload = jaw_preview_parts_payload(
            {"stl_path": json.dumps([{"file": "jaw.stl"}, "skip-me", {"file": "jaw2.stl"}])}
        )

        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[0]["file"], "jaw.stl")
        self.assertEqual(payload[1]["file"], "jaw2.stl")

    def test_measurement_overlays_invalid_json_returns_empty(self):
        from ui.jaw_page_support.preview_rules import jaw_preview_measurement_overlays

        self.assertEqual(jaw_preview_measurement_overlays({"measurement_overlays": "{"}), [])

    def test_transform_signature_normalizes_selected_parts(self):
        from ui.jaw_page_support.preview_rules import jaw_preview_transform_signature

        signature = jaw_preview_transform_signature(
            {
                "preview_plane": "yz",
                "preview_rot_x": "90",
                "preview_rot_y": 0,
                "preview_rot_z": 180,
                "preview_transform_mode": "translate",
                "preview_fine_transform": True,
                "preview_selected_part": "4",
                "preview_selected_parts": ["1", "bad", 3],
            }
        )

        self.assertEqual(signature[0], "YZ")
        self.assertEqual(signature[1:4], (90, 0, 180))
        self.assertEqual(signature[6], 4)
        self.assertEqual(signature[7], (1, 3))


# ===========================================================================
# 9. Selector state + payload mixins
# ===========================================================================

class TestSelectorMixins(unittest.TestCase):

    def setUp(self):
        _prefer_tools_library_namespace()

    def test_build_initial_buckets_normalizes_keys_and_deduplicates(self):
        from ui.selectors.tool_selector_state import ToolSelectorStateMixin

        class _DummyToolState(ToolSelectorStateMixin):
            pass

        dummy = _DummyToolState()
        dummy._current_head = "HEAD2"
        dummy._current_spindle = "sub"

        buckets = dummy._build_initial_buckets(
            initial_assignments=None,
            initial_assignment_buckets={
                "head1/sub": [
                    {"tool_id": "T001", "uid": 1, "tool_head": "HEAD1", "spindle": "sub"},
                    {"tool_id": "T001", "uid": 1, "tool_head": "HEAD1", "spindle": "sub"},
                ],
                "HEAD2:main": [{"tool_id": "T002", "uid": 2}],
            },
        )

        self.assertIn("HEAD1:sub", buckets)
        self.assertIn("HEAD2:main", buckets)
        self.assertIn("HEAD2:sub", buckets)
        self.assertEqual(len(buckets["HEAD1:sub"]), 1)

    def test_tool_selector_send_selector_selection_emits_payload(self):
        from ui.selectors.tool_selector_payload import ToolSelectorPayloadMixin

        class _DummyToolPayload(ToolSelectorPayloadMixin):
            def __init__(self):
                self._assigned_tools = [{"tool_id": "T001", "spindle": "main"}]
                self._assignments_by_target = {"HEAD1:main": [{"tool_id": "T001", "spindle": "main"}]}
                self._current_head = "HEAD1"
                self._current_spindle = "main"
                self._on_submit = object()
                self.captured = None

            def _sync_assignment_order(self):
                return None

            @staticmethod
            def _target_key(head: str, spindle: str) -> str:
                return f"{str(head or '').upper()}:{str(spindle or '').lower()}"

            def _finish_submit(self, callback, payload):
                self.captured = (callback, payload)

        dummy = _DummyToolPayload()
        dummy._send_selector_selection()

        self.assertIsNotNone(dummy.captured)
        callback, payload = dummy.captured
        self.assertIs(callback, dummy._on_submit)
        self.assertEqual(payload["kind"], "tools")
        self.assertEqual(payload["selector_head"], "HEAD1")
        self.assertEqual(payload["selector_spindle"], "main")
        self.assertEqual(payload["selected_items"][0]["tool_id"], "T001")

    def test_jaw_selector_send_selector_selection_emits_slot_payload(self):
        from ui.selectors.jaw_selector_payload import JawSelectorPayloadMixin
        from ui.selectors.jaw_selector_state import JawSelectorStateMixin

        class _DummyJawPayload(JawSelectorPayloadMixin, JawSelectorStateMixin):
            def __init__(self):
                self._selector_assignments = {
                    "main": {"jaw_id": "J001", "jaw_type": "Soft jaws", "spindle_side": "Both"},
                    "sub": {"jaw_id": "J002", "jaw_type": "Hard jaws", "spindle_side": "Sub spindle"},
                }
                self._on_submit = object()
                self.captured = None

            def _finish_submit(self, callback, payload):
                self.captured = (callback, payload)

        dummy = _DummyJawPayload()
        dummy._send_selector_selection()

        self.assertIsNotNone(dummy.captured)
        callback, payload = dummy.captured
        self.assertIs(callback, dummy._on_submit)
        self.assertEqual(payload["kind"], "jaws")
        slots = {item["slot"]: item for item in payload["selected_items"]}
        self.assertIn("main", slots)
        self.assertIn("sub", slots)
        self.assertEqual(slots["main"]["jaw_id"], "J001")
        self.assertEqual(slots["sub"]["jaw_id"], "J002")


class TestSelectorUiWiring(unittest.TestCase):

    def test_build_selector_bottom_bar_wires_cancel_and_done_callbacks(self):
        from ui.selectors.common import build_selector_bottom_bar

        host = QWidget()
        host_layout = QVBoxLayout(host)

        events: list[str] = []
        _, cancel_btn, done_btn = build_selector_bottom_bar(
            host_layout,
            translate=lambda _k, default=None, **_kwargs: default or "",
            on_cancel=lambda: events.append("cancel"),
            on_done=lambda: events.append("done"),
        )

        cancel_btn.click()
        done_btn.click()
        self.assertEqual(events, ["cancel", "done"])

    def test_selector_dialog_base_cancel_notified_once(self):
        from ui.selectors.common import SelectorDialogBase

        events: list[str] = []

        class _DummyDialog(SelectorDialogBase):
            pass

        dialog = _DummyDialog(
            translate=lambda _k, default=None, **_kwargs: default or "",
            on_cancel=lambda: events.append("cancel"),
        )

        dialog._cancel_dialog()
        dialog.close()
        QApplication.processEvents()
        self.assertEqual(events, ["cancel"])

    def test_selected_rows_or_current_uses_current_when_no_selection(self):
        from ui.selectors.common import selected_rows_or_current

        view = QListWidget()
        view.addItem("A")
        view.addItem("B")
        view.setCurrentRow(1)

        indexes = selected_rows_or_current(view)
        self.assertEqual(len(indexes), 1)
        self.assertEqual(indexes[0].row(), 1)

    def test_selected_rows_or_current_prefers_explicit_selection(self):
        from ui.selectors.common import selected_rows_or_current

        view = QListWidget()
        view.setSelectionMode(QListWidget.ExtendedSelection)
        view.addItem("A")
        view.addItem("B")
        view.addItem("C")

        view.item(0).setSelected(True)
        view.item(2).setSelected(True)
        indexes = selected_rows_or_current(view)

        self.assertEqual([idx.row() for idx in indexes], [0, 2])


class TestMainWindowSelectorSessionFlow(unittest.TestCase):

    def setUp(self):
        _prefer_tools_library_namespace()
        self.main_window_module = _load_tool_library_main_window_module()
        self.MainWindow = self.main_window_module.MainWindow

    def test_open_selector_dialog_for_tools_builds_tool_dialog(self):
        built = {}

        class _FakeDialog:
            def __init__(self, **kwargs):
                built.update(kwargs)

        dummy = types.SimpleNamespace(
            _selector_mode="tools",
            tool_service=object(),
            jaw_service=object(),
            machine_profile=object(),
            _selector_head="HEAD1",
            _selector_spindle="main",
            _selector_initial_assignments=[{"tool_id": "T001"}],
            _selector_initial_assignment_buckets={"HEAD1:main": [{"tool_id": "T001"}]},
            _tool_selector_dialog=None,
            _jaw_selector_dialog=None,
            _t=lambda _k, default=None, **_kwargs: default or "",
            _on_selector_dialog_submit=object(),
            _on_selector_dialog_cancel=object(),
            _close_selector_dialogs=lambda: built.setdefault("closed", True),
        )

        with mock.patch.object(self.main_window_module, "ToolSelectorDialog", _FakeDialog):
            self.MainWindow._open_selector_dialog_for_session(dummy, False)

        self.assertTrue(built.get("closed"))
        self.assertIsNotNone(dummy._tool_selector_dialog)
        self.assertEqual(built["selector_head"], "HEAD1")
        self.assertEqual(built["selector_spindle"], "main")
        self.assertEqual(built["initial_assignments"][0]["tool_id"], "T001")

    def test_open_selector_dialog_for_jaws_builds_jaw_dialog(self):
        built = {}

        class _FakeDialog:
            def __init__(self, **kwargs):
                built.update(kwargs)

        dummy = types.SimpleNamespace(
            _selector_mode="jaws",
            tool_service=object(),
            jaw_service=object(),
            machine_profile=object(),
            _selector_head="",
            _selector_spindle="sub",
            _selector_initial_assignments=[{"jaw_id": "J001"}],
            _selector_initial_assignment_buckets={},
            _tool_selector_dialog=None,
            _jaw_selector_dialog=None,
            _t=lambda _k, default=None, **_kwargs: default or "",
            _on_selector_dialog_submit=object(),
            _on_selector_dialog_cancel=object(),
            _close_selector_dialogs=lambda: built.setdefault("closed", True),
        )

        with mock.patch.object(self.main_window_module, "JawSelectorDialog", _FakeDialog):
            self.MainWindow._open_selector_dialog_for_session(dummy, False)

        self.assertTrue(built.get("closed"))
        self.assertIsNotNone(dummy._jaw_selector_dialog)
        self.assertEqual(built["selector_spindle"], "sub")
        self.assertEqual(built["initial_assignments"][0]["jaw_id"], "J001")

    def test_on_selector_dialog_cancel_handoff_only_when_active_session(self):
        events: list[str] = []
        dummy = types.SimpleNamespace(
            _closing_selector_dialogs=False,
            _selector_mode="tools",
            _clear_selector_session=lambda show=False: events.append(f"clear:{show}"),
            _back_to_setup_manager=lambda: events.append("back"),
        )

        self.MainWindow._on_selector_dialog_cancel(dummy)
        self.assertEqual(events, ["clear:False", "back"])

        events.clear()
        dummy._selector_mode = ""
        self.MainWindow._on_selector_dialog_cancel(dummy)
        self.assertEqual(events, [])

    def test_on_selector_dialog_submit_normalizes_and_forwards_payload(self):
        captured = {}
        dummy = types.SimpleNamespace(
            _selector_head="head2",
            _selector_spindle="sub",
            _send_selector_result_payload=lambda **kwargs: captured.update(kwargs),
        )

        self.MainWindow._on_selector_dialog_submit(
            dummy,
            {
                "kind": "TOOLS",
                "selected_items": [{"tool_id": "T001"}],
                "selector_head": "",
                "selector_spindle": "",
                "assignment_buckets_by_target": {"HEAD2:sub": [{"tool_id": "T001"}]},
            },
        )

        self.assertEqual(captured["kind"], "tools")
        self.assertEqual(captured["selector_head"], "HEAD2")
        self.assertEqual(captured["selector_spindle"], "sub")
        self.assertIn("HEAD2:sub", captured["assignment_buckets_by_target"])

    def test_send_selector_result_payload_warns_when_callback_missing(self):
        dummy = types.SimpleNamespace(
            _selector_callback_server="",
            _selector_request_id="REQ-1",
            _t=lambda _k, default=None, **_kwargs: default or "",
            _back_to_setup_manager=lambda: self.fail("handoff should not happen when callback is missing"),
        )

        with mock.patch.object(self.main_window_module.QMessageBox, "warning") as warning_mock:
            self.MainWindow._send_selector_result_payload(
                dummy,
                kind="jaws",
                selected_items=[{"jaw_id": "J001"}],
            )

        warning_mock.assert_called_once()

    def test_send_selector_result_payload_sends_and_handoffs_on_success(self):
        events: list[str] = []

        dummy = types.SimpleNamespace(
            _selector_callback_server="selector-callback",
            _selector_request_id="REQ-2",
            _t=lambda _k, default=None, **_kwargs: default or "",
            _back_to_setup_manager=lambda: events.append("back"),
        )

        def _fake_send_selector_result_payload(_host, **kwargs):
            events.append(f"kind:{kwargs.get('kind')}")
            return True

        with mock.patch.object(
            self.main_window_module,
            "send_selector_result_payload",
            _fake_send_selector_result_payload,
        ):
            self.MainWindow._send_selector_result_payload(
                dummy,
                kind="tools",
                selected_items=[{"tool_id": "T001"}],
                selector_head="HEAD1",
                selector_spindle="main",
                assignment_buckets_by_target={"HEAD1:main": [{"tool_id": "T001"}]},
            )

        self.assertIn("kind:tools", events)
        self.assertIn("back", events)


# ===========================================================================

if __name__ == "__main__":
    unittest.main()
