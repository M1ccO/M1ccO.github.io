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

from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402
from ui.work_editor_dialog import WorkEditorDialog  # noqa: E402

try:
    sys.path.remove(str(_SETUP_ROOT))
except ValueError:
    pass

_APP = QApplication.instance() or QApplication([])


class _StyleProbeDialog(QMainWindow):
    pass


class _WorkEditorStyleProbe(_StyleProbeDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._host_visual_style_applied = False
        self._normal_page = None
        self._selector_page = None
        self.setProperty("workEditorDialog", True)

    def _resolve_style_host(self):
        return WorkEditorDialog._resolve_style_host(self)

    def _load_work_editor_style_sheet_from_disk(self):
        return "QDialog[workEditorDialog=\"true\"] { background: #f5f7fa; }"


class TestWorkEditorStyleInheritance(unittest.TestCase):
    def test_apply_host_visual_style_copies_host_stylesheet(self):
        host = QMainWindow()
        host.setStyleSheet('QDialog[workEditorDialog="true"] QLabel { color: #102030; }')
        host.show()
        _APP.processEvents()

        dlg = _WorkEditorStyleProbe()

        WorkEditorDialog._apply_host_visual_style(dlg)

        self.assertEqual(host.styleSheet(), dlg.styleSheet())
        self.assertTrue(dlg._host_visual_style_applied)

        dlg.close()
        host.close()


if __name__ == "__main__":
    unittest.main()