from __future__ import annotations

import logging
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
_SETUP_ROOT = _WORKSPACE / "Setup Manager"
for _candidate in (_WORKSPACE, _SETUP_ROOT):
    _text = str(_candidate)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from PySide6.QtCore import QEvent, QRect, QSize, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QStackedWidget, QWidget  # noqa: E402
from ui import work_editor_dialog as work_editor_dialog_module  # noqa: E402
from ui.work_editor_dialog import WorkEditorDialog  # noqa: E402

try:
    sys.path.remove(str(_SETUP_ROOT))
except ValueError:
    pass

_APP = QApplication.instance() or QApplication([])


class _GeometryDialog(QDialog):
    _SELECTOR_MIN_WIDTH = 1100
    _SELECTOR_EXPAND_DELTA = 480
    _RESIZE_FOR_SELECTOR_MODE = False
    _SELECTOR_TRANSITION_SHIELD_DELAY_MS = 32
    _LOGGER = logging.getLogger(__name__)

    def __init__(self):
        super().__init__()
        self.resize(900, 640)
        self.setMinimumSize(760, 560)
        self._selector_mode_active = False
        self._selector_open_requested = False
        self._selector_session_serial = 0
        self._selector_session_id = None
        self._selector_session_uuid = None
        self._selector_session_kind = ""
        self._selector_session_phase = "idle"
        self._host_visual_style_applied = False
        self._startup_popup_guard_active = False
        self._selector_restore_state = None
        self._combo_popup_windows = []
        self._raw_part_combo_popup_window = None
        self._raw_part_combo_popup_allowed = False

        self._root_stack = QStackedWidget(self)
        self._normal_page = QWidget(self._root_stack)
        self._selector_page = QWidget(self._root_stack)
        self._selector_overlay_container = QWidget(self._normal_page)
        self._selector_overlay_mount_container = QWidget(self._selector_overlay_container)
        self._selector_mount_container = QWidget(self._selector_page)
        self._selector_transition_shield = QWidget(self)
        self._root_stack.addWidget(self._normal_page)
        self._root_stack.addWidget(self._selector_page)
        self._root_stack.setCurrentWidget(self._normal_page)
        self.tabs = QWidget(self._normal_page)
        self._dialog_buttons = QWidget(self._normal_page)
        self.tabs.setVisible(True)
        self._dialog_buttons.setVisible(True)
        self._selector_transition_shield_pending_hide = False
        self.logged_events = []
        self.closed_popup_count = 0

    def _capture_selector_restore_state(self):
        return WorkEditorDialog._capture_selector_restore_state(self)

    def _restore_from_selector_state(self):
        return WorkEditorDialog._restore_from_selector_state(self)

    def _expand_for_selector_mode(self):
        return WorkEditorDialog._expand_for_selector_mode(self)

    def _clear_selector_session_request(self, session_id=None):
        return WorkEditorDialog._clear_selector_session_request(self, session_id)

    def _resolve_style_host(self):
        return None

    def _load_work_editor_style_sheet_from_disk(self):
        return "QDialog[workEditorDialog=\"true\"] { background: #ffffff; }"

    def _selector_host_uses_overlay_mode(self):
        return WorkEditorDialog._selector_host_uses_overlay_mode(self)

    def _selector_current_mount_container(self):
        return WorkEditorDialog._selector_current_mount_container(self)

    def _sync_selector_overlay_geometry(self):
        return WorkEditorDialog._sync_selector_overlay_geometry(self)

    def _set_selector_overlay_visible(self, visible: bool):
        return WorkEditorDialog._set_selector_overlay_visible(self, visible)

    def _install_selector_transition_trace_filters(self):
        return WorkEditorDialog._install_selector_transition_trace_filters(self)

    def _trace_selector_surface_event(self, obj, event):
        return WorkEditorDialog._trace_selector_surface_event(self, obj, event)

    def _set_normal_editor_surface_hidden_for_selector(self, hidden: bool):
        return WorkEditorDialog._set_normal_editor_surface_hidden_for_selector(self, hidden)

    def _selector_session_uses_transition_shield(self):
        return WorkEditorDialog._selector_session_uses_transition_shield(self)

    def _sync_selector_transition_shield_geometry(self):
        return WorkEditorDialog._sync_selector_transition_shield_geometry(self)

    def _hide_selector_transition_shield(self):
        return WorkEditorDialog._hide_selector_transition_shield(self)

    def _set_selector_transition_shield_visible(self, visible: bool):
        return WorkEditorDialog._set_selector_transition_shield_visible(self, visible)

    def _is_true_popup_window(self, widget):
        return WorkEditorDialog._is_true_popup_window(widget)

    def _release_startup_popup_guard(self, *, reason: str):
        return WorkEditorDialog._release_startup_popup_guard(self, reason=reason)

    def _log_selector_event(self, event: str, **fields):
        self.logged_events.append((event, fields))

    def _trace_startup_event(self, name: str, **fields):
        self.logged_events.append((name, fields))

    def _close_transient_combo_popups(self):
        self.closed_popup_count += 1


class TestWorkEditorGeometryPhase6(unittest.TestCase):
    def test_capture_and_restore_round_trip(self):
        dlg = _GeometryDialog()
        original_geometry = QRect(dlg.geometry())
        original_min = QSize(dlg.minimumSize())
        original_max = QSize(dlg.maximumSize())

        state = WorkEditorDialog._capture_selector_restore_state(dlg)
        dlg.resize(1200, 700)
        dlg.setMinimumSize(1000, 600)
        dlg._selector_restore_state = state

        WorkEditorDialog._restore_from_selector_state(dlg)

        self.assertEqual(original_geometry, dlg.geometry())
        self.assertEqual(original_min, dlg.minimumSize())
        self.assertEqual(original_max, dlg.maximumSize())

    def test_enter_and_exit_selector_mode_switches_stack_and_restores(self):
        dlg = _GeometryDialog()
        original_geometry = QRect(dlg.geometry())
        dlg._selector_open_requested = True
        dlg._selector_session_id = 1
        dlg._selector_session_phase = "requested"

        WorkEditorDialog._enter_selector_mode(dlg)
        self.assertTrue(dlg._selector_mode_active)
        self.assertIs(dlg._root_stack.currentWidget(), dlg._selector_page)
        self.assertGreater(dlg.width(), 0)

        WorkEditorDialog._exit_selector_mode(dlg)
        self.assertFalse(dlg._selector_mode_active)
        self.assertIs(dlg._root_stack.currentWidget(), dlg._normal_page)
        self.assertEqual(original_geometry, dlg.geometry())
        self.assertIsNone(dlg._selector_session_id)
        self.assertFalse(dlg._selector_open_requested)

    def test_enter_and_exit_selector_mode_can_use_overlay_diagnostic_path(self):
        dlg = _GeometryDialog()
        dlg._selector_open_requested = True
        dlg._selector_session_id = 3
        dlg._selector_session_kind = "tools"
        dlg._selector_session_phase = "requested"

        with mock.patch.object(
            work_editor_dialog_module, "WORK_EDITOR_SELECTOR_HOST_DIAGNOSTIC_MODE", "overlay"
        ):
            WorkEditorDialog._enter_selector_mode(dlg)
            self.assertTrue(dlg._selector_mode_active)
            self.assertIs(dlg._root_stack.currentWidget(), dlg._normal_page)
            self.assertFalse(dlg._selector_overlay_container.isHidden())
            self.assertIn(dlg.tabs, dlg._selector_hidden_editor_widgets)
            self.assertIn(dlg._dialog_buttons, dlg._selector_hidden_editor_widgets)
            self.assertTrue(dlg._selector_transition_shield_pending_hide)

            WorkEditorDialog._exit_selector_mode(dlg)

        self.assertFalse(dlg._selector_mode_active)
        self.assertFalse(dlg._selector_overlay_container.isVisible())
        self.assertIs(dlg._root_stack.currentWidget(), dlg._normal_page)
        self.assertEqual([], dlg._selector_hidden_editor_widgets)
        self.assertFalse(dlg._selector_transition_shield.isVisible())

    def test_begin_selector_session_request_blocks_reentry(self):
        dlg = _GeometryDialog()

        session_id = WorkEditorDialog._begin_selector_session_request(dlg, kind="tools")

        self.assertEqual(1, session_id)
        self.assertEqual("tools", dlg._selector_session_kind)
        self.assertTrue(dlg._selector_open_requested)
        self.assertEqual("requested", dlg._selector_session_phase)
        self.assertIsNone(WorkEditorDialog._begin_selector_session_request(dlg, kind="jaws"))

    def test_exit_selector_mode_clears_pending_request_without_active_page(self):
        dlg = _GeometryDialog()
        dlg._selector_open_requested = True
        dlg._selector_session_id = 7
        dlg._selector_session_kind = "tools"
        dlg._selector_session_phase = "mounting"

        WorkEditorDialog._exit_selector_mode(dlg)

        self.assertFalse(dlg._selector_mode_active)
        self.assertFalse(dlg._selector_open_requested)
        self.assertIsNone(dlg._selector_session_id)
        self.assertEqual("", dlg._selector_session_kind)
        self.assertEqual("idle", dlg._selector_session_phase)

    def test_apply_host_visual_style_uses_fallback_stylesheet(self):
        dlg = _GeometryDialog()
        dlg.setProperty("workEditorDialog", True)

        WorkEditorDialog._apply_host_visual_style(dlg)

        self.assertIn("workEditorDialog", dlg.styleSheet())
        self.assertTrue(dlg._host_visual_style_applied)

    def test_install_selector_transition_trace_filters_logs_surface_event(self):
        dlg = _GeometryDialog()
        dlg._selector_trace_widgets = {}

        with mock.patch.object(work_editor_dialog_module, "WORK_EDITOR_SELECTOR_TRACE_PAINT", True):
            WorkEditorDialog._install_selector_transition_trace_filters(dlg)
            dlg._root_stack.setCurrentWidget(dlg._selector_page)
            paint_event = QEvent(QEvent.Paint)
            WorkEditorDialog._trace_selector_surface_event(dlg, dlg._selector_page, paint_event)

        self.assertTrue(any(event == "trace.enabled" for event, _fields in dlg.logged_events))
        self.assertTrue(
            any(
                event == "surface.event"
                and fields.get("watched") == "selector_page"
                and fields.get("qt_event") == "Paint"
                for event, fields in dlg.logged_events
            )
        )

    def test_selector_current_mount_container_uses_overlay_mount_in_overlay_mode(self):
        dlg = _GeometryDialog()
        with mock.patch.object(
            work_editor_dialog_module, "WORK_EDITOR_SELECTOR_HOST_DIAGNOSTIC_MODE", "overlay"
        ):
            mount_container = WorkEditorDialog._selector_current_mount_container(dlg)
        self.assertIs(mount_container, dlg._selector_overlay_mount_container)

    def test_selector_host_auto_mode_keeps_stack_for_tool_sessions(self):
        dlg = _GeometryDialog()
        dlg._selector_session_kind = "tools"
        with mock.patch.object(
            work_editor_dialog_module, "WORK_EDITOR_SELECTOR_HOST_DIAGNOSTIC_MODE", "auto"
        ):
            self.assertFalse(WorkEditorDialog._selector_host_uses_overlay_mode(dlg))

    def test_selector_host_auto_mode_keeps_stack_for_jaw_sessions(self):
        dlg = _GeometryDialog()
        dlg._selector_session_kind = "jaws"
        with mock.patch.object(
            work_editor_dialog_module, "WORK_EDITOR_SELECTOR_HOST_DIAGNOSTIC_MODE", "auto"
        ):
            self.assertFalse(WorkEditorDialog._selector_host_uses_overlay_mode(dlg))

    def test_tool_sessions_skip_transition_shield_in_default_mode(self):
        dlg = _GeometryDialog()
        dlg._selector_session_kind = "tools"
        self.assertFalse(WorkEditorDialog._selector_session_uses_transition_shield(dlg))

    def test_jaw_sessions_skip_transition_shield(self):
        dlg = _GeometryDialog()
        dlg._selector_session_kind = "jaws"
        self.assertFalse(WorkEditorDialog._selector_session_uses_transition_shield(dlg))

if __name__ == "__main__":
    unittest.main()
