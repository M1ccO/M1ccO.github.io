from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
_SETUP_ROOT = _WORKSPACE / "Setup Manager"
for _candidate in (_WORKSPACE, _SETUP_ROOT):
    _text = str(_candidate)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from PySide6.QtCore import QRect, QSize  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QStackedWidget, QWidget  # noqa: E402
from ui.work_editor_dialog import WorkEditorDialog  # noqa: E402

try:
    sys.path.remove(str(_SETUP_ROOT))
except ValueError:
    pass

_APP = QApplication.instance() or QApplication([])


class _GeometryDialog(QDialog):
    _SELECTOR_MIN_WIDTH = 1100
    _SELECTOR_EXPAND_DELTA = 480

    def __init__(self):
        super().__init__()
        self.resize(900, 640)
        self.setMinimumSize(760, 560)
        self._selector_mode_active = False
        self._selector_restore_state = None

        self._root_stack = QStackedWidget(self)
        self._normal_page = QWidget(self._root_stack)
        self._selector_page = QWidget(self._root_stack)
        self._root_stack.addWidget(self._normal_page)
        self._root_stack.addWidget(self._selector_page)
        self._root_stack.setCurrentWidget(self._normal_page)

    def _capture_selector_restore_state(self):
        return WorkEditorDialog._capture_selector_restore_state(self)

    def _restore_from_selector_state(self):
        return WorkEditorDialog._restore_from_selector_state(self)

    def _expand_for_selector_mode(self):
        return WorkEditorDialog._expand_for_selector_mode(self)


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

        WorkEditorDialog._enter_selector_mode(dlg)
        self.assertTrue(dlg._selector_mode_active)
        self.assertIs(dlg._root_stack.currentWidget(), dlg._selector_page)
        self.assertGreater(dlg.width(), 0)

        WorkEditorDialog._exit_selector_mode(dlg)
        self.assertFalse(dlg._selector_mode_active)
        self.assertIs(dlg._root_stack.currentWidget(), dlg._normal_page)
        self.assertEqual(original_geometry, dlg.geometry())


if __name__ == "__main__":
    unittest.main()
