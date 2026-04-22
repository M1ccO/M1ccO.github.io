from __future__ import annotations

import sys
import unittest
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QWidget


_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
if str(_WORKSPACE) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE))

from shared.ui.helpers.detached_preview_common import (  # noqa: E402
    create_detached_preview_dialog,
    uses_independent_detached_preview_host,
)


class TestSelectorPreviewHosting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_standalone_selector_uses_independent_preview_host(self):
        selector = QDialog()
        selector.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        self.assertTrue(uses_independent_detached_preview_host(selector))

        dialog = create_detached_preview_dialog(
            selector,
            title="3D Preview",
            on_finished=lambda _result: None,
        )

        self.assertIsNone(dialog.parent())
        self.assertTrue(bool(dialog.windowFlags() & Qt.Tool))
        self.assertTrue(bool(dialog.windowFlags() & Qt.WindowStaysOnTopHint))
        dialog.deleteLater()
        selector.deleteLater()

    def test_regular_page_uses_top_level_host_window_as_parent(self):
        main_window = QMainWindow()
        page = QWidget(main_window)

        self.assertFalse(uses_independent_detached_preview_host(page))

        dialog = create_detached_preview_dialog(
            page,
            title="3D Preview",
            on_finished=lambda _result: None,
        )

        self.assertIs(dialog.parent(), main_window)
        dialog.deleteLater()
        page.deleteLater()
        main_window.deleteLater()

    def test_regular_page_can_request_independent_preview_host(self):
        main_window = QMainWindow()
        page = QWidget(main_window)
        page._detached_preview_force_independent_host = True

        dialog = create_detached_preview_dialog(
            page,
            title="3D Preview",
            on_finished=lambda _result: None,
        )

        self.assertIsNone(dialog.parent())
        self.assertTrue(bool(dialog.windowFlags() & Qt.Tool))
        dialog.deleteLater()
        page.deleteLater()
        main_window.deleteLater()


if __name__ == "__main__":
    unittest.main()