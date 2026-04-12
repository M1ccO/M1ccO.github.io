"""Shared main-window helpers used by both apps.

Contains neutral primitives that both main_window.py files duplicate:
- THEME_PALETTES: identical color theme dictionary
- get_active_theme_palette: resolve theme name to palette dict
- current_window_rect: Win32-based on-screen geometry query
- fade_out_and: non-animated page-switch helper
- fade_in: non-animated opacity restore
- is_interactive_widget: parent-walk check for background-click deselection
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes

from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QComboBox,
    QLineEdit,
    QSplitter,
    QWidget,
)


# ── Theme palettes ──────────────────────────────────────────────────

THEME_PALETTES: dict[str, dict[str, str]] = {
    "classic": {
        "surface_bg": "rgba(205, 212, 238, 0.97)",
        "detail_box_bg": "rgba(232, 240, 250, 0.98)",
    },
    "graphite": {
        "surface_bg": "rgba(168, 179, 198, 0.98)",
        "detail_box_bg": "rgba(207, 217, 233, 0.98)",
    },
}


def get_active_theme_palette(preferences: dict) -> dict[str, str]:
    """Return the active theme palette dict from user preferences."""
    theme_name = preferences.get("color_theme", "classic")
    return THEME_PALETTES.get(theme_name, THEME_PALETTES["classic"])


# ── Window geometry ─────────────────────────────────────────────────

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


# ── Fade helpers ────────────────────────────────────────────────────

def fade_out_and(window, callback, *, pre_callback=None):
    """Immediately run *callback* without transition animation.

    *pre_callback* is invoked after stopping any in-flight animation but
    before *callback*; apps can use it for side-effects like re-enabling
    graphics effects.
    """
    if getattr(window, '_fade_anim', None) is not None:
        window._fade_anim.stop()
    window._fade_anim = None
    window.setWindowOpacity(1.0)
    if pre_callback is not None:
        pre_callback()
    callback()


def fade_in(window, *, post_restore=None):
    """Show fully visible without transition animation.

    *post_restore* is invoked after opacity is reset; apps can use it
    for side-effects like re-enabling graphics effects.
    """
    if getattr(window, '_fade_anim', None) is not None:
        window._fade_anim.stop()
    window._fade_anim = None
    window.setWindowOpacity(1.0)
    if post_restore is not None:
        post_restore()


# ── Background-click deselection ────────────────────────────────────

def is_interactive_widget_click(obj: QWidget, window: QWidget) -> bool:
    """Return True if *obj* is inside an interactive widget tree.

    Used by both apps to decide whether a background click should
    clear the active page's catalog selection.
    """
    if not isinstance(obj, QWidget) or obj.window() is not window:
        return True  # not our window — treat as "don't clear"
    widget = obj
    while widget is not None:
        if isinstance(widget, (QAbstractButton, QComboBox, QLineEdit, QAbstractItemView, QSplitter)):
            return True
        widget = widget.parentWidget()
    return False
