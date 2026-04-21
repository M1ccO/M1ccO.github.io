from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
for _candidate in (_WORKSPACE,):
    _text = str(_candidate)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget  # noqa: E402

from shared.ui.main_window_helpers import capture_window_snapshot  # noqa: E402

_APP = QApplication.instance() or QApplication([])


class TestMainWindowHelpersSnapshot(unittest.TestCase):
    def test_capture_window_snapshot_returns_pixmap_for_visible_widget(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("Snapshot"))
        widget.resize(220, 90)
        widget.show()
        _APP.processEvents()

        pixmap = capture_window_snapshot(widget)

        self.assertIsNotNone(pixmap)
        self.assertFalse(pixmap.isNull())
        self.assertGreater(pixmap.width(), 0)
        self.assertGreater(pixmap.height(), 0)

        widget.close()
        widget.deleteLater()
        _APP.processEvents()

    def test_capture_window_snapshot_returns_none_for_hidden_widget(self) -> None:
        widget = QWidget()
        widget.resize(120, 60)

        pixmap = capture_window_snapshot(widget)

        self.assertIsNone(pixmap)
        widget.deleteLater()
        _APP.processEvents()


if __name__ == "__main__":
    unittest.main()