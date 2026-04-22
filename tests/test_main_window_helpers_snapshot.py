from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
for _candidate in (_WORKSPACE,):
    _text = str(_candidate)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from PySide6.QtGui import QPixmap  # noqa: E402
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

    def test_capture_window_snapshot_prefers_full_screen_region_grab(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("Snapshot"))
        widget.resize(220, 90)
        widget.show()
        _APP.processEvents()

        expected = QPixmap(320, 180)
        expected.fill()

        class _DummyScreen:
            def __init__(self):
                self.calls = []

            def grabWindow(self, *args):
                self.calls.append(args)
                return expected

        screen = _DummyScreen()

        with patch("shared.ui.main_window_helpers.current_window_rect", return_value=(10, 20, 320, 180)), \
             patch("shared.ui.main_window_helpers.QGuiApplication.screenAt", return_value=screen), \
             patch("shared.ui.main_window_helpers.QGuiApplication.primaryScreen", return_value=screen):
            pixmap = capture_window_snapshot(widget)

        self.assertIs(pixmap, expected)
        self.assertEqual([(0, 10, 20, 320, 180)], screen.calls)

        widget.close()
        widget.deleteLater()
        _APP.processEvents()


if __name__ == "__main__":
    unittest.main()