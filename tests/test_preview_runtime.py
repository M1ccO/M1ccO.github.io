from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QDialog, QWidget

_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
for _candidate in (_WORKSPACE,):
    _text = str(_candidate)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from shared.ui.helpers.preview_runtime import (  # noqa: E402
    claim_prewarmed_preview_widget,
    preview_runtime_ready,
    register_preview_runtime_widget,
)

_APP = QApplication.instance() or QApplication([])


class _PreviewWidget(QWidget):
    pass


class TestPreviewRuntime(unittest.TestCase):
    def setUp(self) -> None:
        _APP._preview_warmup_widget = None
        _APP._preview_runtime_ready = False
        self._widgets: list[QWidget] = []
        self._dialogs: list[QDialog] = []

    def tearDown(self) -> None:
        for dialog in self._dialogs:
            try:
                dialog.close()
                dialog.deleteLater()
            except Exception:
                pass
        for widget in self._widgets:
            try:
                widget.close()
                widget.deleteLater()
            except Exception:
                pass
        QCoreApplication.sendPostedEvents(None, 0)
        _APP.processEvents()
        _APP._preview_warmup_widget = None
        _APP._preview_runtime_ready = False

    def test_register_marks_runtime_ready(self) -> None:
        widget = _PreviewWidget()
        self._widgets.append(widget)

        register_preview_runtime_widget(widget)

        self.assertTrue(preview_runtime_ready())
        self.assertIs(widget, _APP._preview_warmup_widget)

    def test_claim_reparents_top_level_warmup_widget(self) -> None:
        warmup = _PreviewWidget()
        self._widgets.append(warmup)
        register_preview_runtime_widget(warmup)
        dialog = QDialog()
        self._dialogs.append(dialog)

        claimed = claim_prewarmed_preview_widget(dialog)

        self.assertIs(warmup, claimed)
        self.assertIs(dialog, warmup.parentWidget())
        self.assertTrue(preview_runtime_ready())

    def test_claim_does_not_steal_parented_preview_widget(self) -> None:
        parent_dialog = QDialog()
        self._dialogs.append(parent_dialog)
        warmup = _PreviewWidget(parent_dialog)
        self._widgets.append(warmup)
        register_preview_runtime_widget(warmup)
        other_dialog = QDialog()
        self._dialogs.append(other_dialog)

        claimed = claim_prewarmed_preview_widget(other_dialog)

        self.assertIsNone(claimed)
        self.assertIs(parent_dialog, warmup.parentWidget())


if __name__ == "__main__":
    unittest.main()