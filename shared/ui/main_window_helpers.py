"""Shared main-window helpers used by both apps."""

from __future__ import annotations

import ctypes
import ctypes.wintypes

from PySide6.QtWidgets import QAbstractButton, QAbstractItemView, QComboBox, QLineEdit, QSplitter, QWidget

from shared.ui.theme import THEME_PALETTES, get_active_theme_palette


def current_window_rect(window) -> tuple[int, int, int, int]:
    """Return the actual on-screen window rectangle, including snap placement."""
    try:
        rect = ctypes.wintypes.RECT()
        hwnd = int(window.winId())
        if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    except Exception:
        pass
    geom = window.frameGeometry()
    return geom.x(), geom.y(), geom.width(), geom.height()


def fade_out_and(window, callback, *, pre_callback=None):
    """Immediately run *callback* without transition animation."""
    if getattr(window, "_fade_anim", None) is not None:
        window._fade_anim.stop()
    window._fade_anim = None
    if pre_callback is not None:
        pre_callback()
    callback()


def fade_in(window, *, post_restore=None):
    """Show fully visible without transition animation."""
    if getattr(window, "_fade_anim", None) is not None:
        window._fade_anim.stop()
    window._fade_anim = None
    window.setWindowOpacity(1.0)
    if post_restore is not None:
        post_restore()


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
