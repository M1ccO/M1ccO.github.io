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

from PySide6.QtWidgets import QApplication, QDialog, QWidget  # noqa: E402
from ui.setup_page_support import batch_actions, crud_actions  # noqa: E402
from ui.setup_page_support.work_editor_launch import (  # noqa: E402
    exec_work_editor_dialog,
    prime_work_editor_dialog,
    resolve_work_editor_parent,
)

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

        dialog = _DialogStub()

        prime_work_editor_dialog(dialog)
        prime_work_editor_dialog(dialog)

        self.assertEqual(1, events.count("ensurePolished"))
        self.assertEqual(1, events.count("layout.activate"))
        self.assertIn("surface", events)
        self.assertIn("content", events)
        self.assertIn("updateGeometry", events)

    def test_prime_work_editor_dialog_warmup_surfaces_runs_once(self):
        class _DialogStub(QDialog):
            def __init__(self):
                super().__init__()
                self._startup_open_primed = False
                self.warmup_called = 0
                self._layout = SimpleNamespace(activate=lambda: None)

            def layout(self):
                return self._layout

            def _warmup_initial_interaction_surfaces(self):
                self.warmup_called += 1

        dialog = _DialogStub()

        prime_work_editor_dialog(dialog)
        prime_work_editor_dialog(dialog)

        self.assertEqual(1, dialog.warmup_called)

    def test_exec_work_editor_dialog_primes_before_exec(self):
        events = []

        class _DialogStub(QDialog):
            def __init__(self):
                super().__init__()
                self._startup_open_primed = False
                self._layout = SimpleNamespace(activate=lambda: events.append("layout.activate"))

            def setAttribute(self, attr, value):
                events.append(("setAttribute", str(attr), value))

            def show(self):
                events.append("show")

            def hide(self):
                events.append("hide")

            def layout(self):
                return self._layout

            def exec(self):
                events.append("exec")
                return 1

            def setWindowOpacity(self, value):
                events.append(("opacity", value))

        dialog = _DialogStub()

        result = exec_work_editor_dialog(dialog)

        self.assertEqual(1, result)
        self.assertIn("exec", events)

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


if __name__ == "__main__":
    unittest.main()
