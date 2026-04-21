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

from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget  # noqa: E402

from shared.ui.transition_shell import (  # noqa: E402
    cancel_sender_transition,
    complete_sender_transition,
    prepare_sender_transition,
)
from shared.ui.transition_shell_config import TransitionShellMode, init_transition_shell_config  # noqa: E402

_APP = QApplication.instance() or QApplication([])


class TestTransitionShell(unittest.TestCase):
    def tearDown(self) -> None:
        init_transition_shell_config(TransitionShellMode.SENDER_FADE.value)

    def _build_window(self) -> QWidget:
        window = QWidget()
        layout = QVBoxLayout(window)
        layout.addWidget(QLabel("Sender shell"))
        window.resize(260, 100)
        window.show()
        _APP.processEvents()
        return window

    def _cleanup_window(self, window: QWidget) -> None:
        cancel_sender_transition(window)
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, 0)
        _APP.processEvents()

    def test_prepare_sender_transition_captures_snapshot_and_geometry(self) -> None:
        init_transition_shell_config(TransitionShellMode.SENDER_FADE.value)
        window = self._build_window()

        prepared = prepare_sender_transition(window, geometry=(10, 20, 260, 100))

        state = getattr(window, "_pending_sender_transition", None)
        self.assertTrue(prepared)
        self.assertIsNotNone(state)
        self.assertEqual((10, 20, 260, 100), state.geometry)
        self.assertFalse(state.snapshot.isNull())
        self.assertFalse(window.isVisible())
        self.assertIsNotNone(getattr(window, "_active_transition_shell", None))

        self._cleanup_window(window)

    def test_cancel_sender_transition_restores_hidden_sender(self) -> None:
        init_transition_shell_config(TransitionShellMode.SENDER_FADE.value)
        window = self._build_window()
        prepare_sender_transition(window, geometry=(15, 25, 260, 100))

        cancel_sender_transition(window)
        _APP.processEvents()

        self.assertTrue(window.isVisible())
        self.assertIsNone(getattr(window, "_pending_sender_transition", None))
        self.assertIsNone(getattr(window, "_active_transition_shell", None))

        self._cleanup_window(window)

    def test_complete_sender_transition_falls_back_to_hide_when_disabled(self) -> None:
        init_transition_shell_config(TransitionShellMode.DISABLED.value)
        window = self._build_window()

        completed = complete_sender_transition(window)

        self.assertFalse(completed)
        self.assertFalse(window.isVisible())
        self._cleanup_window(window)

    def test_complete_sender_transition_hides_sender_and_clears_shell(self) -> None:
        config = init_transition_shell_config(TransitionShellMode.SENDER_FADE.value)
        config.reveal_delay_ms = 0
        config.fade_duration_ms = 0
        config.shell_min_show_ms = 0
        window = self._build_window()
        prepare_sender_transition(window, geometry=(30, 40, 260, 100))

        completed = complete_sender_transition(window)
        QCoreApplication.sendPostedEvents(None, 0)
        _APP.processEvents()

        self.assertTrue(completed)
        self.assertFalse(window.isVisible())
        self.assertIsNone(getattr(window, "_pending_sender_transition", None))
        self.assertIsNone(getattr(window, "_active_transition_shell", None))

        self._cleanup_window(window)


if __name__ == "__main__":
    unittest.main()