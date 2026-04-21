from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from shared.ui.main_window_helpers import capture_window_snapshot, current_window_rect
from shared.ui.transition_shell_config import TransitionShellMode, get_transition_shell_config


LOG = logging.getLogger(__name__)
SENDER_TRANSITION_COMPLETE_COMMAND = "complete_sender_transition"


@dataclass(slots=True)
class _PendingSenderTransition:
    snapshot: QPixmap
    geometry: tuple[int, int, int, int]
    prepared_at: float
    sender_was_visible: bool
    completing: bool = False


class _SnapshotShell(QWidget):
    def __init__(self, snapshot: QPixmap, geometry: tuple[int, int, int, int]) -> None:
        flags = Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint
        for flag_name in ("WindowDoesNotAcceptFocus", "WindowTransparentForInput"):
            extra_flag = getattr(Qt, flag_name, None)
            if extra_flag is None:
                extra_flag = getattr(Qt.WindowType, flag_name, None)
            if extra_flag is not None:
                flags |= extra_flag
        super().__init__(None, flags)
        self._snapshot = snapshot
        self._fade_anim: QPropertyAnimation | None = None
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setFocusPolicy(Qt.NoFocus)
        x, y, width, height = geometry
        self.setGeometry(x, y, width, height)
        self.setWindowOpacity(1.0)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(self.rect(), self._snapshot)

    def fade_out(self, duration_ms: int, finished_callback) -> None:
        if duration_ms <= 0:
            QTimer.singleShot(0, finished_callback)
            return

        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(duration_ms)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(finished_callback)
        self._fade_anim = anim
        anim.start()


def _hide_sender_window(window: QWidget) -> None:
    try:
        window.hide()
    except Exception:
        pass


def _restore_sender_window(window: QWidget, *, geometry: tuple[int, int, int, int] | None = None) -> None:
    try:
        if geometry is not None:
            x, y, width, height = geometry
            window.setGeometry(x, y, width, height)
    except Exception:
        pass
    try:
        window.setWindowOpacity(1.0)
    except Exception:
        pass
    try:
        if window.isMinimized():
            window.showNormal()
        else:
            window.show()
        window.raise_()
        window.activateWindow()
    except Exception:
        pass


def _clear_active_shell(window: QWidget, shell: QWidget | None) -> None:
    if shell is not None and getattr(window, "_active_transition_shell", None) is shell:
        window._active_transition_shell = None


def _create_snapshot_shell(window: QWidget, state: _PendingSenderTransition) -> _SnapshotShell | None:
    try:
        shell = _SnapshotShell(state.snapshot, state.geometry)
    except Exception:
        return None

    def _on_destroyed(*_args) -> None:
        _clear_active_shell(window, shell)

    window._active_transition_shell = shell
    shell.destroyed.connect(_on_destroyed)
    shell.show()
    shell.raise_()

    app = QApplication.instance()
    if app is not None:
        try:
            app.processEvents()
        except Exception:
            pass
    return shell
    try:
        window.setWindowOpacity(1.0)
    except Exception:
        pass


def cancel_sender_transition(window: QWidget | None) -> None:
    if window is None:
        return

    state = getattr(window, "_pending_sender_transition", None)
    shell = getattr(window, "_active_transition_shell", None)
    window._pending_sender_transition = None
    if shell is not None:
        try:
            shell.close()
        except Exception:
            pass
    window._active_transition_shell = None
    if state is not None and not state.completing and state.sender_was_visible:
        _restore_sender_window(window, geometry=state.geometry)


def prepare_sender_transition(
    window: QWidget | None,
    *,
    geometry: tuple[int, int, int, int] | None = None,
) -> bool:
    if window is None:
        return False

    cancel_sender_transition(window)
    config = get_transition_shell_config()
    if not config.enabled or config.mode != TransitionShellMode.SENDER_FADE:
        return False

    snapshot = capture_window_snapshot(window)
    if snapshot is None:
        return False

    rect = geometry or current_window_rect(window)
    state = _PendingSenderTransition(
        snapshot=snapshot,
        geometry=tuple(int(value) for value in rect),
        prepared_at=time.monotonic(),
        sender_was_visible=bool(window.isVisible() and not window.isMinimized()),
    )
    window._pending_sender_transition = state

    shell = _create_snapshot_shell(window, state)
    if shell is None:
        window._pending_sender_transition = None
        window._active_transition_shell = None
        return False

    _hide_sender_window(window)
    return True


def complete_sender_transition(window: QWidget | None) -> bool:
    if window is None:
        return False

    config = get_transition_shell_config()
    state = getattr(window, "_pending_sender_transition", None)
    shell = getattr(window, "_active_transition_shell", None)

    if (
        state is None
        or not config.enabled
        or config.mode != TransitionShellMode.SENDER_FADE
        or state.snapshot.isNull()
    ):
        window._pending_sender_transition = None
        _hide_sender_window(window)
        return False

    if state.completing:
        return True

    if shell is None:
        shell = _create_snapshot_shell(window, state)
        if shell is None:
            window._pending_sender_transition = None
            _hide_sender_window(window)
            return False
        _hide_sender_window(window)

    state.completing = True

    def _finish() -> None:
        window._pending_sender_transition = None
        _clear_active_shell(window, shell)
        try:
            shell.close()
        except Exception:
            pass
        LOG.debug(
            "complete_sender_transition: fade_ms=%s prepared_latency_ms=%s",
            max(0, int(config.fade_duration_ms)),
            int((time.monotonic() - state.prepared_at) * 1000),
        )

    reveal_delay_ms = max(0, int(config.reveal_delay_ms))
    fade_duration_ms = max(0, int(config.fade_duration_ms))
    min_show_ms = max(0, int(config.shell_min_show_ms))
    effective_fade_ms = max(fade_duration_ms, max(0, min_show_ms - reveal_delay_ms))

    def _start_fade() -> None:
        shell.fade_out(effective_fade_ms, _finish)

    if reveal_delay_ms <= 0:
        _start_fade()
    else:
        QTimer.singleShot(reveal_delay_ms, _start_fade)
    return True