"""Tests for PreloadManager wiring resolvers at startup.

Per WORK_EDITOR_SELECTOR_ARCHITECTURE_BLUEPRINT.md (CODE PATH INDEX).
Uses stubbed library modules to avoid opening real sqlite files.
"""

from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Make `services.preload_manager` importable without the app-level sys.path
# munging that main.py performs.
_SETUP_MANAGER_DIR = Path(__file__).resolve().parent.parent / "Setup Manager"
if str(_SETUP_MANAGER_DIR) in sys.path:
    sys.path.remove(str(_SETUP_MANAGER_DIR))
sys.path.insert(0, str(_SETUP_MANAGER_DIR))
for _mod_name in list(sys.modules.keys()):
    if _mod_name == "services" or _mod_name.startswith("services."):
        sys.modules.pop(_mod_name, None)

from services.preload_manager import PreloadManager, reset_preload_manager_for_tests  # noqa: E402
from shared.selector.payloads import SpindleKey, ToolBucket  # noqa: E402
from shared.ui.resolvers import (  # noqa: E402
    ResolverNotConfiguredError,
    get_resolver,
    set_resolver,
)


class _StubDB:
    def __init__(self, path):
        self.path = path
        self.conn = types.SimpleNamespace(close=lambda: None)


class _StubToolService:
    def __init__(self, db):
        self.db = db
        self._records = {
            "T01": {"id": "T01", "description": "OD", "tool_type": "Turning", "pot_number": 1},
        }
        self.calls: list[str] = []

    def get_tool(self, tool_id):
        self.calls.append(tool_id)
        return self._records.get(tool_id)


class _StubJawService:
    def __init__(self, db):
        self.db = db
        self._records = {
            "J1": {"jaw_id": "J1", "jaw_type": "Soft jaws", "spindle_side": "Main spindle"},
        }
        self.calls: list[str] = []

    def get_jaw(self, jaw_id):
        self.calls.append(jaw_id)
        return self._records.get(jaw_id)


class _StubFixtureService:
    def __init__(self, db):
        self.db = db


def _install_library_stubs():
    """Replace tools_and_jaws_library imports with in-memory stubs."""
    root = types.ModuleType("tools_and_jaws_library")
    data_pkg = types.ModuleType("tools_and_jaws_library.data")
    services_pkg = types.ModuleType("tools_and_jaws_library.services")
    db_mod = types.ModuleType("tools_and_jaws_library.data.database")
    jaw_db_mod = types.ModuleType("tools_and_jaws_library.data.jaw_database")
    fixture_db_mod = types.ModuleType("tools_and_jaws_library.data.fixture_database")
    tool_svc_mod = types.ModuleType("tools_and_jaws_library.services.tool_service")
    jaw_svc_mod = types.ModuleType("tools_and_jaws_library.services.jaw_service")
    fixture_svc_mod = types.ModuleType("tools_and_jaws_library.services.fixture_service")

    db_mod.Database = _StubDB
    jaw_db_mod.JawDatabase = _StubDB
    fixture_db_mod.FixtureDatabase = _StubDB
    tool_svc_mod.ToolService = _StubToolService
    jaw_svc_mod.JawService = _StubJawService
    fixture_svc_mod.FixtureService = _StubFixtureService

    saved = {}
    for name, mod in [
        ("tools_and_jaws_library", root),
        ("tools_and_jaws_library.data", data_pkg),
        ("tools_and_jaws_library.services", services_pkg),
        ("tools_and_jaws_library.data.database", db_mod),
        ("tools_and_jaws_library.data.jaw_database", jaw_db_mod),
        ("tools_and_jaws_library.data.fixture_database", fixture_db_mod),
        ("tools_and_jaws_library.services.tool_service", tool_svc_mod),
        ("tools_and_jaws_library.services.jaw_service", jaw_svc_mod),
        ("tools_and_jaws_library.services.fixture_service", fixture_svc_mod),
    ]:
        saved[name] = sys.modules.get(name)
        sys.modules[name] = mod
    return saved


def _restore_library_modules(saved):
    for name, original in saved.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


class _FakeDrawService:
    def __init__(self, tool_db_path="/tmp/tools.db", jaw_db_path="/tmp/jaws.db", fixture_db_path="/tmp/fixtures.db"):
        self.tool_db_path = tool_db_path
        self.jaw_db_path = jaw_db_path
        self.fixture_db_path = fixture_db_path


class PreloadManagerTests(unittest.TestCase):
    def setUp(self):
        self._saved = _install_library_stubs()
        reset_preload_manager_for_tests()
        set_resolver("tool", None)
        set_resolver("jaw", None)

    def tearDown(self):
        reset_preload_manager_for_tests()
        set_resolver("tool", None)
        set_resolver("jaw", None)
        _restore_library_modules(self._saved)

    def test_initialize_registers_resolvers(self):
        mgr = PreloadManager()
        ok = mgr.initialize(_FakeDrawService())
        self.assertTrue(ok)
        self.assertTrue(mgr.initialized)
        tool_resolver = get_resolver("tool")
        self.assertIsNotNone(tool_resolver)
        resolved = tool_resolver.resolve_tool("T01", bucket=ToolBucket.MAIN)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.tool_id, "T01")

    def test_initialize_with_none_draw_service_returns_false(self):
        mgr = PreloadManager()
        self.assertFalse(mgr.initialize(None))
        with self.assertRaises(ResolverNotConfiguredError):
            get_resolver("tool")

    def test_refresh_swaps_services(self):
        mgr = PreloadManager()
        mgr.initialize(_FakeDrawService(tool_db_path="/tmp/a.db"))
        first = mgr.tool_service
        mgr.refresh(_FakeDrawService(tool_db_path="/tmp/b.db"))
        second = mgr.tool_service
        self.assertIsNot(first, second)
        self.assertEqual(Path(second.db.path), Path("/tmp/b.db"))

    def test_shutdown_clears_registry(self):
        mgr = PreloadManager()
        mgr.initialize(_FakeDrawService())
        mgr.shutdown()
        self.assertFalse(mgr.initialized)
        with self.assertRaises(ResolverNotConfiguredError):
            get_resolver("tool")
        with self.assertRaises(ResolverNotConfiguredError):
            get_resolver("jaw")

    def test_bump_revisions_invalidates_both_caches(self):
        mgr = PreloadManager()
        mgr.initialize(_FakeDrawService())
        tool_r = mgr.tool_resolver
        jaw_r = mgr.jaw_resolver
        assert tool_r is not None and jaw_r is not None
        rev_t = tool_r.library_rev
        rev_j = jaw_r.library_rev
        mgr.bump_revisions()
        self.assertEqual(tool_r.library_rev, rev_t + 1)
        self.assertEqual(jaw_r.library_rev, rev_j + 1)

    def test_jaw_resolution_roundtrip(self):
        mgr = PreloadManager()
        mgr.initialize(_FakeDrawService())
        jaw_r = get_resolver("jaw")
        resolved = jaw_r.resolve_jaw("J1", spindle=SpindleKey.MAIN)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.jaw_id, "J1")
        self.assertEqual(resolved.spindle, SpindleKey.MAIN)

    def test_initialize_triggers_preview_warmup(self):
        mgr = PreloadManager()
        with mock.patch.object(mgr, "_warm_preview_engine") as warmup:
            mgr.initialize(_FakeDrawService())
        warmup.assert_called_once()

    def test_refresh_triggers_preview_warmup_again(self):
        mgr = PreloadManager()
        mgr.initialize(_FakeDrawService())
        with mock.patch.object(mgr, "_warm_preview_engine") as warmup:
            mgr.refresh(_FakeDrawService(tool_db_path="/tmp/other.db"))
        warmup.assert_called_once()

    def test_initialize_exposes_fixture_service(self):
        mgr = PreloadManager()
        mgr.initialize(_FakeDrawService())
        self.assertIsNotNone(mgr.fixture_service)
        self.assertIsInstance(mgr.fixture_service, _StubFixtureService)

    def test_shutdown_clears_fixture_service(self):
        mgr = PreloadManager()
        mgr.initialize(_FakeDrawService())
        mgr.shutdown()
        self.assertIsNone(mgr.fixture_service)


class PreloadManagerInvalidationTests(unittest.TestCase):
    def setUp(self):
        self._saved = _install_library_stubs()
        reset_preload_manager_for_tests()
        set_resolver("tool", None)
        set_resolver("jaw", None)
        self.mgr = PreloadManager()
        self.mgr.initialize(_FakeDrawService())

    def tearDown(self):
        self.mgr.shutdown()
        reset_preload_manager_for_tests()
        set_resolver("tool", None)
        set_resolver("jaw", None)
        _restore_library_modules(self._saved)

    def test_invalidate_tool_specific_id(self):
        tool_r = self.mgr.tool_resolver
        assert tool_r is not None
        tool_r.resolve_tool("T01", bucket=ToolBucket.MAIN)
        rev = tool_r.library_rev
        self.mgr.invalidate("tool", ["T01"])
        self.assertEqual(tool_r.library_rev, rev)
        tool_r.resolve_tool("T01", bucket=ToolBucket.MAIN)
        self.assertEqual(self.mgr.tool_service.calls, ["T01", "T01"])

    def test_invalidate_tool_without_ids_bumps_rev(self):
        tool_r = self.mgr.tool_resolver
        assert tool_r is not None
        rev = tool_r.library_rev
        self.mgr.invalidate("tool", [])
        self.assertEqual(tool_r.library_rev, rev + 1)

    def test_invalidate_jaw_specific_id(self):
        jaw_r = self.mgr.jaw_resolver
        assert jaw_r is not None
        jaw_r.resolve_jaw("J1", spindle=SpindleKey.MAIN)
        self.mgr.invalidate("jaw", ["J1"])
        jaw_r.resolve_jaw("J1", spindle=SpindleKey.MAIN)
        self.assertEqual(self.mgr.jaw_service.calls, ["J1", "J1"])

    def test_invalidate_all_bumps_both(self):
        tool_r = self.mgr.tool_resolver
        jaw_r = self.mgr.jaw_resolver
        assert tool_r is not None and jaw_r is not None
        rev_t = tool_r.library_rev
        rev_j = jaw_r.library_rev
        self.mgr.invalidate("all")
        self.assertEqual(tool_r.library_rev, rev_t + 1)
        self.assertEqual(jaw_r.library_rev, rev_j + 1)

    def test_invalidate_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            self.mgr.invalidate("fixture", ["F1"])

    def test_listener_receives_kind_and_ids(self):
        received: list[tuple[str, tuple[str, ...]]] = []
        self.mgr.add_listener(lambda kind, ids: received.append((kind, ids)))
        self.mgr.invalidate("tool", ["T01", "T02"])
        self.mgr.invalidate("jaw", ["J1"])
        self.mgr.bump_revisions()
        self.assertEqual(received[0], ("tool", ("T01", "T02")))
        self.assertEqual(received[1], ("jaw", ("J1",)))
        self.assertEqual(received[-1], ("all", ()))

    def test_listener_remove(self):
        received: list[tuple[str, tuple[str, ...]]] = []
        listener = lambda kind, ids: received.append((kind, ids))
        self.mgr.add_listener(listener)
        self.mgr.invalidate("tool", ["T01"])
        self.mgr.remove_listener(listener)
        self.mgr.invalidate("tool", ["T02"])
        self.assertEqual(len(received), 1)

    def test_listener_exception_is_swallowed(self):
        def boom(kind, ids):
            raise RuntimeError("listener failed")
        self.mgr.add_listener(boom)
        self.mgr.invalidate("tool", ["T01"])  # should not raise

    def test_listener_duplicates_ignored(self):
        received: list[tuple[str, tuple[str, ...]]] = []
        listener = lambda kind, ids: received.append((kind, ids))
        self.mgr.add_listener(listener)
        self.mgr.add_listener(listener)
        self.mgr.invalidate("tool", ["T01"])
        self.assertEqual(len(received), 1)

    def test_listener_non_callable_rejected(self):
        with self.assertRaises(TypeError):
            self.mgr.add_listener("not callable")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
