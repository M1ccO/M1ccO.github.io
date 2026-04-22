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
from unittest.mock import patch  # noqa: E402

from shared.ui.transition_shell import (  # noqa: E402
    cancel_receiver_ready_signal,
    cancel_sender_transition,
    complete_sender_transition,
    prepare_sender_transition,
    prepare_receiver_transition,
    reveal_receiver_transition,
    schedule_sender_transition_complete_on_receiver_ready,
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
        cancel_receiver_ready_signal(window)
        cancel_sender_transition(window)
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, 0)
        _APP.processEvents()

    def _drain_events(self, turns: int = 6) -> None:
        for _ in range(max(1, int(turns))):
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
        self.assertTrue(window.isVisible())
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

    def test_prepare_receiver_transition_sets_opacity_zero(self) -> None:
        init_transition_shell_config(TransitionShellMode.SENDER_FADE.value)
        window = self._build_window()

        prepared = prepare_receiver_transition(window)

        self.assertTrue(prepared)
        self.assertEqual(0.0, window.windowOpacity())

        self._cleanup_window(window)

    def test_reveal_receiver_transition_uses_window_fade_in_when_available(self) -> None:
        window = self._build_window()
        calls: list[str] = []

        def _fake_fade_in() -> None:
            calls.append("fade")
            window.setWindowOpacity(1.0)

        window.setWindowOpacity(0.0)
        window.fade_in = _fake_fade_in  # type: ignore[attr-defined]

        revealed = reveal_receiver_transition(window)

        self.assertTrue(revealed)
        self.assertEqual(["fade"], calls)
        self.assertEqual(1.0, window.windowOpacity())

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

    def test_complete_sender_transition_keeps_sender_opaque_until_shell_fade_starts(self) -> None:
        config = init_transition_shell_config(TransitionShellMode.SENDER_FADE.value)
        config.reveal_delay_ms = 0
        config.fade_duration_ms = 100
        config.shell_min_show_ms = 0
        window = self._build_window()
        self.assertTrue(prepare_sender_transition(window, geometry=(30, 40, 260, 100)))
        shell = getattr(window, "_active_transition_shell", None)
        self.assertIsNotNone(shell)

        observed_opacity: list[float] = []

        def _fake_fade_out(_duration_ms: int, finished_callback) -> None:
            observed_opacity.append(float(window.windowOpacity()))
            finished_callback()

        with patch.object(shell, "fade_out", side_effect=_fake_fade_out):
            completed = complete_sender_transition(window)
            self._drain_events(4)

        self.assertTrue(completed)
        self.assertEqual([1.0], observed_opacity)
        self.assertFalse(window.isVisible())

        self._cleanup_window(window)

    def test_schedule_sender_transition_complete_on_receiver_ready_waits_for_stable_geometry(self) -> None:
        window = self._build_window()
        callback_hits: list[str] = []
        rect_samples = [
            (10, 20, 260, 100),
            (10, 20, 260, 100),
        ]

        with patch("shared.ui.transition_shell.current_window_rect", side_effect=lambda _window: rect_samples.pop(0) if rect_samples else (10, 20, 260, 100)):
            scheduled = schedule_sender_transition_complete_on_receiver_ready(
                window,
                callback=lambda: callback_hits.append("ready"),
                geometry_text="10,20,260,100",
                poll_interval_ms=0,
                max_wait_ms=200,
                required_stable_samples=2,
            )
            self._drain_events(8)

        self.assertTrue(scheduled)
        self.assertEqual(["ready"], callback_hits)
        self.assertIsNone(getattr(window, "_pending_receiver_ready_signal", None))
        self.assertIsNone(getattr(window, "_pending_receiver_ready_timer", None))

        self._cleanup_window(window)

    def test_schedule_sender_transition_complete_on_receiver_ready_waits_until_geometry_matches(self) -> None:
        window = self._build_window()
        callback_hits: list[str] = []
        rect_samples = [
            (0, 0, 200, 80),
            (10, 20, 260, 100),
            (10, 20, 260, 100),
        ]

        with patch("shared.ui.transition_shell.current_window_rect", side_effect=lambda _window: rect_samples.pop(0) if rect_samples else (10, 20, 260, 100)):
            schedule_sender_transition_complete_on_receiver_ready(
                window,
                callback=lambda: callback_hits.append("ready"),
                geometry_text="10,20,260,100",
                poll_interval_ms=0,
                max_wait_ms=200,
                required_stable_samples=2,
            )
            self._drain_events(10)

        self.assertEqual(["ready"], callback_hits)

        self._cleanup_window(window)

    def test_prepare_sender_transition_reuses_persistent_shell_host(self) -> None:
        config = init_transition_shell_config(TransitionShellMode.SENDER_FADE.value)
        config.reveal_delay_ms = 0
        config.fade_duration_ms = 0
        config.shell_min_show_ms = 0
        window = self._build_window()

        self.assertTrue(prepare_sender_transition(window, geometry=(10, 20, 260, 100)))
        first_shell = getattr(window, "_active_transition_shell", None)
        self.assertIs(first_shell, getattr(window, "_transition_shell_host", None))

        self.assertTrue(complete_sender_transition(window))
        self._drain_events(6)
        self.assertFalse(first_shell.isVisible())

        window.show()
        self._drain_events(4)

        self.assertTrue(prepare_sender_transition(window, geometry=(30, 40, 260, 100)))
        second_shell = getattr(window, "_active_transition_shell", None)

        self.assertIs(first_shell, second_shell)
        self.assertEqual((30, 40, 260, 100), second_shell.geometry().getRect())

        self._cleanup_window(window)


if __name__ == "__main__":
    unittest.main()