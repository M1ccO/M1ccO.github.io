"""Shared main-window helpers used by both apps."""

from __future__ import annotations

import ctypes
import ctypes.wintypes

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer
from PySide6.QtWidgets import QAbstractButton, QAbstractItemView, QComboBox, QLineEdit, QSplitter, QWidget

from shared.ui.theme import THEME_PALETTES, get_active_theme_palette

_FADE_IN_MS = 250
_FADE_OUT_MS = 250
_DWMWA_EXTENDED_FRAME_BOUNDS = 9


def _window_rect_from_hwnd(hwnd: int) -> tuple[int, int, int, int] | None:
    try:
        rect = ctypes.wintypes.RECT()
        if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    except Exception:
        pass
    return None


def _visible_frame_bounds_from_hwnd(hwnd: int) -> tuple[int, int, int, int] | None:
    try:
        rect = ctypes.wintypes.RECT()
        dwmapi = getattr(ctypes.windll, "dwmapi", None)
        if dwmapi is None:
            return None
        result = dwmapi.DwmGetWindowAttribute(
            hwnd,
            _DWMWA_EXTENDED_FRAME_BOUNDS,
            ctypes.byref(rect),
            ctypes.sizeof(rect),
        )
        if result == 0:
            return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    except Exception:
        pass
    return None


def _window_frame_insets_from_hwnd(hwnd: int) -> tuple[int, int, int, int] | None:
    raw_rect = _window_rect_from_hwnd(hwnd)
    visible_rect = _visible_frame_bounds_from_hwnd(hwnd)
    if raw_rect is None or visible_rect is None:
        return None

    raw_x, raw_y, raw_w, raw_h = raw_rect
    visible_x, visible_y, visible_w, visible_h = visible_rect
    raw_right = raw_x + raw_w
    raw_bottom = raw_y + raw_h
    visible_right = visible_x + visible_w
    visible_bottom = visible_y + visible_h

    return (
        max(0, visible_x - raw_x),
        max(0, visible_y - raw_y),
        max(0, raw_right - visible_right),
        max(0, raw_bottom - visible_bottom),
    )


def current_window_rect(window) -> tuple[int, int, int, int]:
    """Return the actual visible on-screen window rectangle, including snap placement."""
    try:
        hwnd = int(window.winId())
        visible_rect = _visible_frame_bounds_from_hwnd(hwnd)
        if visible_rect is not None:
            return visible_rect

        raw_rect = _window_rect_from_hwnd(hwnd)
        if raw_rect is not None:
            return raw_rect
    except Exception:
        pass
    geom = window.frameGeometry()
    return geom.x(), geom.y(), geom.width(), geom.height()


def parse_frame_geometry_string(geometry_text: str) -> tuple[int, int, int, int] | None:
    """Parse an ``x,y,width,height`` frame-geometry string."""
    try:
        x, y, width, height = (int(v) for v in str(geometry_text or "").split(","))
    except Exception:
        return None
    if x == -32000 and y == -32000:
        return None
    if width <= 0 or height <= 0:
        return None
    return x, y, width, height


def _cancel_pending_frame_geometry(window) -> None:
    pending = getattr(window, "_pending_frame_geometry_timers", None)
    if not pending:
        window._pending_frame_geometry_timers = []
        return
    for timer in pending:
        try:
            timer.stop()
        except Exception:
            pass
        try:
            timer.deleteLater()
        except Exception:
            pass
    window._pending_frame_geometry_timers = []


def _apply_frame_geometry_once(window, x: int, y: int, width: int, height: int) -> bool:
    try:
        hwnd = int(window.winId())
        translated_x = x
        translated_y = y
        translated_width = width
        translated_height = height
        insets = _window_frame_insets_from_hwnd(hwnd)
        if insets is not None:
            left_inset, top_inset, right_inset, bottom_inset = insets
            translated_x = x - left_inset
            translated_y = y - top_inset
            translated_width = width + left_inset + right_inset
            translated_height = height + top_inset + bottom_inset
        SWP_NOZORDER = 0x0004
        SWP_NOACTIVATE = 0x0010
        applied = bool(
            ctypes.windll.user32.SetWindowPos(
                hwnd,
                0,
                translated_x,
                translated_y,
                translated_width,
                translated_height,
                SWP_NOZORDER | SWP_NOACTIVATE,
            )
        )
        if applied:
            return True
    except Exception:
        pass

    try:
        frame = window.frameGeometry()
        frame_w_extra = max(0, frame.width() - window.width())
        frame_h_extra = max(0, frame.height() - window.height())
        client_w = max(320, width - frame_w_extra)
        client_h = max(260, height - frame_h_extra)
        window.resize(client_w, client_h)
        window.move(x, y)
        return True
    except Exception:
        return False


def apply_frame_geometry_string(window, geometry_text: str, *, retry_delays_ms: tuple[int, ...] = ()) -> bool:
    """Apply a frame-geometry string immediately and optionally reapply it later."""
    rect = parse_frame_geometry_string(geometry_text)
    if rect is None:
        _cancel_pending_frame_geometry(window)
        return False

    _cancel_pending_frame_geometry(window)
    x, y, width, height = rect
    applied = _apply_frame_geometry_once(window, x, y, width, height)

    pending: list[QTimer] = []

    def _reapply() -> None:
        _apply_frame_geometry_once(window, x, y, width, height)

    for delay in retry_delays_ms:
        timer = QTimer(window)
        timer.setSingleShot(True)
        timer.timeout.connect(_reapply)
        timer.start(max(0, int(delay)))
        pending.append(timer)

    window._pending_frame_geometry_timers = pending
    return applied


def fade_out_and(window, callback, *, pre_callback=None):
    """Fade window to transparent then run *callback* (typically hide/close).

    The window must stay visible during the animation so Windows keeps the
    layered HWND compositing active. callback fires after the animation.
    """
    if getattr(window, "_fade_anim", None) is not None:
        window._fade_anim.stop()
        window._fade_anim = None
    # Cancel any pending delayed fade-in (e.g. user clicks back before the
    # 250 ms Library fade-in window elapses).
    _pending = getattr(window, "_pending_fade_in_timer", None)
    if _pending is not None:
        try:
            _pending.stop()
        except Exception:
            pass
        window._pending_fade_in_timer = None
    if pre_callback is not None:
        pre_callback()
    start = window.windowOpacity()
    if start <= 0.0:
        QTimer.singleShot(0, callback)
        return
    # Drive fade-out with a QTimer so the callback is guaranteed to fire even
    # if QPropertyAnimation.finished is blocked by graphics-effect resets or
    # window state changes on Windows.
    _steps = 20
    _interval = max(1, _FADE_OUT_MS // _steps)
    _step_size = start / _steps
    _current = [start]

    def _tick() -> None:
        _current[0] = max(0.0, _current[0] - _step_size)
        window.setWindowOpacity(_current[0])
        if _current[0] <= 0.0:
            t = getattr(window, "_fade_anim", None)
            if t is not None:
                t.stop()
            window._fade_anim = None
            QTimer.singleShot(0, callback)

    t = QTimer(window)
    t.setInterval(_interval)
    t.timeout.connect(_tick)
    window._fade_anim = t
    t.start()


def fade_in(window, *, post_restore=None):
    """Animate window from transparent to fully visible.

    Caller must have already called setWindowOpacity(0.0) and show() so that
    Windows creates a layered HWND before the animation begins.
    """
    if getattr(window, "_fade_anim", None) is not None:
        window._fade_anim.stop()
        window._fade_anim = None
    # If opacity is already 1.0 somehow (e.g. animation was interrupted),
    # snap to 0 so the fade is always visible.
    if window.windowOpacity() >= 1.0:
        window.setWindowOpacity(0.0)
    anim = QPropertyAnimation(window, b'windowOpacity', window)
    anim.setDuration(_FADE_IN_MS)
    anim.setStartValue(window.windowOpacity())
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    if post_restore is not None:
        anim.finished.connect(post_restore)
    window._fade_anim = anim
    anim.start()


def is_interactive_widget_click(obj: QWidget, window: QWidget) -> bool:
    """Return True if *obj* is inside an interactive widget tree."""
    if not isinstance(obj, QWidget) or obj.window() is not window:
        return True
    widget = obj
    while widget is not None:
        if isinstance(widget, (QAbstractButton, QComboBox, QLineEdit, QAbstractItemView, QSplitter)):
            return True
        widget = widget.parentWidget()
    return False
