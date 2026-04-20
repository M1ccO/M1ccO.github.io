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
from ui.work_editor_support.selector_session_controller import WorkEditorSelectorController  # noqa: E402
import ui.work_editor_support.selector_session_controller as ctrl_module  # noqa: E402

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
        self._host_visual_style_applied = False
        self._startup_popup_guard_active = False
        self._selector_cache_merge_enabled = False
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
        self.logged_events = []
        self.closed_popup_count = 0

        self._selector_ctrl = WorkEditorSelectorController(self)

    def _resolve_style_host(self):
        return None

    def _load_work_editor_style_sheet_from_disk(self):
        return 'QDialog[workEditorDialog="true"] { background: #ffffff; }'

    def _is_true_popup_window(self, widget):
        return WorkEditorDialog._is_true_popup_window(self, widget)

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
        ctrl = dlg._selector_ctrl
        original_geometry = QRect(dlg.geometry())
        original_min = QSize(dlg.minimumSize())
        original_max = QSize(dlg.maximumSize())

        state = ctrl._capture_restore_state()
        dlg.resize(1200, 700)
        dlg.setMinimumSize(1000, 600)
        ctrl._restore_state = state

        ctrl._restore_from_state()

        self.assertEqual(original_geometry, dlg.geometry())
        self.assertEqual(original_min, dlg.minimumSize())
        self.assertEqual(original_max, dlg.maximumSize())

    def test_enter_and_exit_selector_mode_switches_stack_and_restores(self):
        dlg = _GeometryDialog()
        ctrl = dlg._selector_ctrl
        original_geometry = QRect(dlg.geometry())
        ctrl._open_requested = True

        ctrl._enter_mode()
        self.assertTrue(ctrl._mode_active)
        self.assertIs(dlg._root_stack.currentWidget(), dlg._selector_page)
        self.assertGreater(dlg.width(), 0)

        ctrl._exit_mode()
        self.assertFalse(ctrl._mode_active)
        self.assertIs(dlg._root_stack.currentWidget(), dlg._normal_page)
        self.assertEqual(original_geometry, dlg.geometry())
        self.assertFalse(ctrl._open_requested)

    def test_enter_and_exit_selector_mode_can_use_overlay_diagnostic_path(self):
        dlg = _GeometryDialog()
        ctrl = dlg._selector_ctrl
        ctrl._open_requested = True

        with mock.patch.object(
            ctrl_module, "WORK_EDITOR_SELECTOR_HOST_DIAGNOSTIC_MODE", "overlay"
        ):
            ctrl._enter_mode()
            self.assertTrue(ctrl._mode_active)
            self.assertIs(dlg._root_stack.currentWidget(), dlg._normal_page)
            self.assertFalse(dlg._selector_overlay_container.isHidden())
            self.assertIn(dlg.tabs, ctrl._hidden_editor_widgets)
            self.assertIn(dlg._dialog_buttons, ctrl._hidden_editor_widgets)
            self.assertTrue(ctrl._transition_shield_pending_hide)

            ctrl._exit_mode()

        self.assertFalse(ctrl._mode_active)
        self.assertFalse(dlg._selector_overlay_container.isVisible())
        self.assertIs(dlg._root_stack.currentWidget(), dlg._normal_page)
        self.assertEqual([], ctrl._hidden_editor_widgets)
        self.assertFalse(dlg._selector_transition_shield.isVisible())

    def test_coordinator_blocks_reentry(self):
        dlg = _GeometryDialog()
        ctrl = dlg._selector_ctrl

        session_id = ctrl._coordinator.request_open(caller="tools")
        self.assertIsNotNone(session_id)
        self.assertTrue(ctrl._coordinator.is_busy)

        with self.assertRaises(Exception) as ctx:
            ctrl._coordinator.request_open(caller="jaws")
        self.assertIn("busy", str(ctx.exception).lower())

    def test_exit_selector_mode_clears_pending_request_without_active_page(self):
        dlg = _GeometryDialog()
        ctrl = dlg._selector_ctrl
        ctrl._open_requested = True

        ctrl._exit_mode()

        self.assertFalse(ctrl._mode_active)
        self.assertFalse(ctrl._open_requested)

    def test_apply_host_visual_style_uses_fallback_stylesheet(self):
        dlg = _GeometryDialog()
        dlg.setProperty("workEditorDialog", True)

        WorkEditorDialog._apply_host_visual_style(dlg)

        self.assertIn("workEditorDialog", dlg.styleSheet())
        self.assertTrue(dlg._host_visual_style_applied)

    def test_install_selector_transition_trace_filters_populates_trace_widgets(self):
        dlg = _GeometryDialog()
        ctrl = dlg._selector_ctrl

        with mock.patch.object(ctrl_module, "WORK_EDITOR_SELECTOR_TRACE_PAINT", True):
            ctrl.install_trace_filters()
            dlg._root_stack.setCurrentWidget(dlg._selector_page)
            paint_event = QEvent(QEvent.Paint)
            ctrl.trace_surface_event(dlg._selector_page, paint_event)

        self.assertGreater(len(ctrl._trace_widgets), 0)

    def test_selector_current_mount_container_uses_overlay_mount_in_overlay_mode(self):
        dlg = _GeometryDialog()
        ctrl = dlg._selector_ctrl
        with mock.patch.object(
            ctrl_module, "WORK_EDITOR_SELECTOR_HOST_DIAGNOSTIC_MODE", "overlay"
        ):
            mount_container = ctrl._current_mount_container()
        self.assertIs(mount_container, dlg._selector_overlay_mount_container)

    def test_host_auto_mode_keeps_stack(self):
        dlg = _GeometryDialog()
        ctrl = dlg._selector_ctrl
        with mock.patch.object(
            ctrl_module, "WORK_EDITOR_SELECTOR_HOST_DIAGNOSTIC_MODE", "auto"
        ):
            self.assertFalse(ctrl._host_uses_overlay_mode())

    def test_default_mode_skips_transition_shield(self):
        dlg = _GeometryDialog()
        ctrl = dlg._selector_ctrl
        self.assertFalse(ctrl._uses_transition_shield())

if __name__ == "__main__":
    unittest.main()
