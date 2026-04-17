from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
_SETUP_ROOT = _WORKSPACE / "Setup Manager"
for _candidate in (_WORKSPACE, _SETUP_ROOT):
    _text = str(_candidate)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from PySide6.QtGui import QShowEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QWidget  # noqa: E402
import ui.main_window as main_window_module  # noqa: E402
from ui.setup_page_support import batch_actions, crud_actions  # noqa: E402
from ui.setup_page_support.work_editor_launch import (  # noqa: E402
    exec_work_editor_dialog,
    prime_work_editor_dialog,
    resolve_work_editor_parent,
)
from ui.work_editor_dialog import WorkEditorDialog  # noqa: E402
from ui.work_editor_support.dialog_lifecycle import setup_tabs  # noqa: E402

try:
    sys.path.remove(str(_SETUP_ROOT))
except ValueError:
    pass

_APP = QApplication.instance() or QApplication([])


class _HostWindow(QWidget):
    pass


class _PageStub(QWidget):
    def __init__(self, host: QWidget):
        super().__init__(host)
        self.draw_service = object()
        self.drawings_enabled = True
        self.work_service = SimpleNamespace(
            get_machine_profile_key=lambda: "lathe_1sp_1h",
            get_work=lambda _work_id: {"work_id": _work_id},
            save_work=lambda _payload: None,
        )
        self.refresh_works = lambda: None
        self._selected_work_ids = lambda: ["W001"]
        self._t = lambda _key, default=None, **_kwargs: default or ""


class TestWorkEditorLaunchParent(unittest.TestCase):
    def test_setup_tabs_parents_pages_to_tab_widget(self):
        class _DialogStub(QWidget):
            def __init__(self):
                super().__init__()
                self._t = lambda _key, default=None, **_kwargs: default or ""

        dialog = _DialogStub()
        setup_tabs(dialog)

        self.assertIs(dialog.tabs.parent(), dialog)
        self.assertGreaterEqual(dialog.tabs.indexOf(dialog.general_tab), 0)
        self.assertGreaterEqual(dialog.tabs.indexOf(dialog.zeros_tab), 0)
        self.assertGreaterEqual(dialog.tabs.indexOf(dialog.tools_tab), 0)
        self.assertGreaterEqual(dialog.tabs.indexOf(dialog.notes_tab), 0)

    def test_resolve_work_editor_parent_returns_top_level_window(self):
        host = _HostWindow()
        page = _PageStub(host)

        self.assertIs(host, resolve_work_editor_parent(page))

    def test_create_work_uses_top_level_parent(self):
        host = _HostWindow()
        page = _PageStub(host)
        captured = {}

        class _DialogStub:
            def __init__(self, *_args, **kwargs):
                captured.update(kwargs)

            def exec(self):
                return 0

        with mock.patch.object(crud_actions, "WorkEditorDialog", _DialogStub):
            crud_actions.create_work(page)

        self.assertIsNone(captured["parent"])
        self.assertIs(host, captured["style_host"])

    def test_edit_work_uses_top_level_parent(self):
        host = _HostWindow()
        page = _PageStub(host)
        captured = {}

        class _DialogStub:
            def __init__(self, *_args, **kwargs):
                captured.update(kwargs)

            def exec(self):
                return 0

        with mock.patch.object(crud_actions, "WorkEditorDialog", _DialogStub):
            crud_actions.edit_work(page)

        self.assertIsNone(captured["parent"])
        self.assertIs(host, captured["style_host"])

    def test_create_work_reuses_cached_dialog_on_cancel(self):
        host = _HostWindow()
        page = _PageStub(host)
        created = {"count": 0}

        class _DialogStub:
            def __init__(self, *_args, **kwargs):
                created["count"] += 1
                self.work = dict(kwargs.get("work") or {})

            def exec(self):
                return 0

        with mock.patch.object(crud_actions, "WorkEditorDialog", _DialogStub):
            crud_actions.create_work(page)
            crud_actions.create_work(page)

        self.assertEqual(1, created["count"])

    def test_edit_work_reuses_cached_dialog_for_same_work(self):
        host = _HostWindow()
        page = _PageStub(host)
        created = {"count": 0}

        class _DialogStub:
            def __init__(self, *_args, **kwargs):
                created["count"] += 1
                self.work = dict(kwargs.get("work") or {})

            def exec(self):
                return 0

        with mock.patch.object(crud_actions, "WorkEditorDialog", _DialogStub):
            crud_actions.edit_work(page)
            crud_actions.edit_work(page)

        self.assertEqual(1, created["count"])

    def test_group_edit_uses_top_level_parent(self):
        host = _HostWindow()
        page = _PageStub(host)
        captured = {}

        class _DialogStub:
            def __init__(self, *_args, **kwargs):
                captured.update(kwargs)

            def get_work_data(self):
                return {}

            def exec(self):
                return 0

        with mock.patch.object(batch_actions, "WorkEditorDialog", _DialogStub):
            batch_actions.group_edit_works(page, ["W001", "W002"])

        self.assertIsNone(captured["parent"])
        self.assertIs(host, captured["style_host"])

    def test_prime_work_editor_dialog_runs_once(self):
        events = []

        class _DialogStub(QDialog):
            def __init__(self):
                super().__init__()
                self._startup_open_primed = False
                self._layout = SimpleNamespace()

            def ensurePolished(self):
                events.append("ensurePolished")

            def _close_transient_combo_popups(self):
                events.append("close_popups")

        dialog = _DialogStub()

        prime_work_editor_dialog(dialog)
        prime_work_editor_dialog(dialog)

        self.assertEqual(1, events.count("ensurePolished"))
        self.assertEqual(1, events.count("close_popups"))

    def test_prime_work_editor_dialog_warmup_surfaces_runs_once(self):
        class _DialogStub(QDialog):
            def __init__(self):
                super().__init__()
                self._startup_open_primed = False
                self.warmup_called = 0

            def _warmup_initial_interaction_surfaces(self):
                self.warmup_called += 1

        dialog = _DialogStub()

        prime_work_editor_dialog(dialog)
        prime_work_editor_dialog(dialog)

        self.assertEqual(0, dialog.warmup_called)

    def test_exec_work_editor_dialog_primes_before_exec(self):
        events = []

        class _DialogStub(QDialog):
            def __init__(self):
                super().__init__()
                self._startup_open_primed = False

            def setAttribute(self, attr, value):
                events.append(("setAttribute", str(attr), value))

            def show(self):
                events.append("show")

            def hide(self):
                events.append("hide")

            def exec(self):
                events.append("exec")
                return 1

            def setWindowOpacity(self, value):
                events.append(("opacity", value))

        dialog = _DialogStub()

        result = exec_work_editor_dialog(dialog)

        self.assertEqual(1, result)
        self.assertIn("exec", events)
        self.assertNotIn("layout.activate", events)

    def test_exec_work_editor_dialog_pauses_and_resumes_preload(self):
        events = []

        class _Host(QWidget):
            def isVisible(self):
                return True

            def isMinimized(self):
                return False

            def hide(self):
                events.append("host.hide")

            def show(self):
                events.append("host.show")

            def raise_(self):
                events.append("host.raise")

            def activateWindow(self):
                events.append("host.activate")

        class _DialogStub(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self._startup_open_primed = False
                self._layout = SimpleNamespace(activate=lambda: events.append("layout.activate"))

            def ensurePolished(self):
                events.append("ensurePolished")

            def layout(self):
                return self._layout

            def _ensure_normal_editor_surface_visible(self):
                events.append("surface")

            def _ensure_normal_editor_content_visible(self):
                events.append("content")

            def _close_transient_combo_popups(self):
                events.append("close_popups")

            def updateGeometry(self):
                events.append("updateGeometry")

            def exec(self):
                events.append("exec")
                return 1

        host = _Host()
        host._tool_library_preload_pause_count = 0
        host._tool_library_preload_completed = False
        host._tool_library_preload_scheduled = False
        dialog = _DialogStub(parent=host)

        result = exec_work_editor_dialog(dialog)

        self.assertEqual(1, result)
        self.assertEqual(0, host._tool_library_preload_pause_count)
        self.assertTrue(host._tool_library_preload_scheduled)
        self.assertNotIn("host.hide", events)
        self.assertNotIn("host.show", events)

    def test_main_window_show_event_does_not_queue_work_editor_preload(self):
        class _WorkService:
            def __init__(self):
                self.db = SimpleNamespace(path=str(_WORKSPACE / "temp" / "setup.sqlite"))

            def get_machine_profile_key(self):
                return "lathe_1sp_1h"

            def list_works(self, _search):
                return []

        class _LogbookService:
            def latest_entries_by_work_ids(self, _ids):
                return {}

            def list_entries(self, _search, filters=None):
                return []

            def delete_entry(self, _entry_id):
                return None

            def export_entries_to_excel(self, _entries, _path, headers=None):
                return None

        class _DrawService:
            def get_reference_source_status(self):
                return {
                    "tool_db_path": str(_WORKSPACE / "temp" / "tool.sqlite"),
                    "tool_db_exists": False,
                    "jaw_db_path": str(_WORKSPACE / "temp" / "jaw.sqlite"),
                    "jaw_db_exists": False,
                    "fixture_db_path": str(_WORKSPACE / "temp" / "fixture.sqlite"),
                    "fixture_db_exists": False,
                }

            def list_drawings_with_context(self, *_args, **_kwargs):
                return []

            def open_drawing(self, _path):
                return True

        class _PrintService:
            def set_reference_service(self, _service):
                pass

            def set_translator(self, _translator):
                pass

        class _MachineConfigService:
            def is_empty(self):
                return True

            def get_active_config(self):
                return None

            def migrate_empty_db_paths(self, *_args, **_kwargs):
                pass

            def migrate_to_config_folders(self):
                pass

        window = main_window_module.MainWindow(
            _WorkService(),
            _LogbookService(),
            _DrawService(),
            _PrintService(),
            _MachineConfigService(),
        )

        with mock.patch.object(window.setup_page, "preload_work_editor_dialog") as preload_mock, mock.patch.object(
            main_window_module.QTimer,
            "singleShot",
        ) as single_shot_mock:
            window.showEvent(QShowEvent())

        preload_mock.assert_not_called()
        single_shot_mock.assert_not_called()

    def test_work_editor_show_event_applies_style_without_hidden_reveal(self):
        class _DialogStub(WorkEditorDialog):
            def __init__(self):
                QDialog.__init__(self)
                self._host_visual_style_applied = False
                self.calls = []

            def _apply_host_visual_style(self):
                self.calls.append("style")

        dialog = _DialogStub()

        WorkEditorDialog.showEvent(dialog, QShowEvent())

        self.assertEqual(["style"], dialog.calls)


if __name__ == "__main__":
    unittest.main()
