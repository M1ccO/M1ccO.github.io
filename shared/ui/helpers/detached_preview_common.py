"""Shared detached-preview shell helpers used by TOOLS and JAWS pages."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QIcon, QKeySequence, QShortcut, QGuiApplication
from PySide6.QtWidgets import QDialog


def uses_independent_detached_preview_host(page) -> bool:
    """Return True when detached preview should not be parented to ``page``.

    Standalone selector dialogs are top-level transient tool windows. Parenting
    detached preview directly to them can cause focus/visibility churn on
    Windows when the preview is opened. In that case, use an independent tool
    window for preview while still tying lifetime back to the selector.
    """
    if page is None or not hasattr(page, "window"):
        return False
    try:
        host_window = page.window()
    except Exception:
        return False
    if host_window is None or host_window is not page:
        return False
    try:
        return bool(host_window.windowFlags() & Qt.WindowStaysOnTopHint)
    except Exception:
        return False


def create_detached_preview_dialog(page, *, title: str, on_finished: Callable[[int], None]) -> QDialog:
    """Create a detached preview dialog with selector-safe ownership rules."""
    independent_host = uses_independent_detached_preview_host(page)
    dialog_parent = None if independent_host else page
    dialog = QDialog(dialog_parent)
    dialog.setProperty('detachedPreviewDialog', True)

    host_window = None
    if page is not None and hasattr(page, "window"):
        try:
            host_window = page.window()
        except Exception:
            host_window = None

    if independent_host:
        dialog.setWindowFlag(Qt.Tool, True)
        dialog.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        dialog.setAttribute(Qt.WA_StyledBackground, True)
        dialog.setAutoFillBackground(True)
        if host_window is not None:
            try:
                dialog.setPalette(host_window.palette())
            except Exception:
                pass
            try:
                stylesheet = str(host_window.styleSheet() or "")
            except Exception:
                stylesheet = ""
            if stylesheet.strip():
                dialog.setStyleSheet(stylesheet)
        try:
            page.destroyed.connect(dialog.close)
        except Exception:
            pass
    elif host_window is not None and bool(host_window.windowFlags() & Qt.WindowStaysOnTopHint):
        dialog.setWindowFlag(Qt.Tool, True)

    dialog.setWindowTitle(title)
    dialog.finished.connect(on_finished)
    return dialog


def bind_escape_close_shortcut(page, dialog, attr_name: str = "_close_preview_shortcut") -> None:
    """Attach an Escape shortcut that closes the provided detached preview dialog."""
    shortcut = QShortcut(QKeySequence(Qt.Key_Escape), dialog)
    shortcut.setContext(Qt.WidgetWithChildrenShortcut)
    shortcut.activated.connect(dialog.close)
    setattr(page, attr_name, shortcut)


def set_preview_button_checked(page, checked: bool, button_attr: str = "preview_window_btn") -> None:
    """Set preview toggle button state without emitting clicked signals."""
    button = getattr(page, button_attr, None)
    if button is None:
        return
    button.blockSignals(True)
    button.setChecked(checked)
    button.blockSignals(False)


def apply_detached_preview_default_bounds(page, dialog_attr: str = "_detached_preview_dialog") -> None:
    """Position detached preview dialog to span from main window content top to frame bottom."""
    dialog = getattr(page, dialog_attr, None)
    if dialog is None:
        return

    host_window = page.window()
    if host_window is None:
        return

    host_frame = host_window.frameGeometry()
    host_geom = host_window.geometry()
    if host_frame.width() <= 0 or host_frame.height() <= 0:
        return

    width = min(max(520, int(host_frame.width() * 0.37)), 700)
    # Height: from content top to frame bottom
    height = host_frame.bottom() - host_geom.top()
    x = host_frame.right() - width + 1
    y = host_geom.top()  # Start at content area top
    
    # Clamp position to screen bounds, preserving exact height
    probe = QPoint(x + 20, y + 20)
    screen = QGuiApplication.screenAt(probe) or QGuiApplication.primaryScreen()
    if screen is not None:
        avail = screen.availableGeometry()
        x = max(avail.left(), min(x, avail.right() - width + 1))
        y = max(avail.top(), min(y, avail.bottom() - height + 1))
    
    dialog.setGeometry(x, y, width, height)


def update_measurement_toggle_icon(
    page,
    enabled: bool,
    *,
    button_attr: str = "_measurement_toggle_btn",
    icons_dir: Path,
    translate: Callable[..., str],
    hide_key: str,
    show_key: str,
    hide_default: str,
    show_default: str,
) -> None:
    """Update detached-preview measurement toggle icon and tooltip."""
    button = getattr(page, button_attr, None)
    if button is None:
        return

    icon_name = "comment_disable.svg" if enabled else "comment.svg"
    button.setIcon(QIcon(str(icons_dir / icon_name)))
    button.setToolTip(
        translate(
            hide_key if enabled else show_key,
            hide_default if enabled else show_default,
        )
    )


def close_detached_preview(page, *, dialog_attr: str = "_detached_preview_dialog", button_attr: str = "preview_window_btn") -> None:
    """Close detached preview dialog, or uncheck preview toggle if dialog is absent."""
    dialog = getattr(page, dialog_attr, None)
    if dialog is not None:
        dialog.close()
    else:
        set_preview_button_checked(page, False, button_attr=button_attr)


def toggle_preview_window(page, *, sync_callback: Callable[[bool], bool], close_callback: Callable[[], None], button_attr: str = "preview_window_btn") -> None:
    """Handle common detached-preview toggle behavior."""
    button = getattr(page, button_attr, None)
    if button is None:
        return

    if button.isChecked():
        if not sync_callback(True):
            set_preview_button_checked(page, False, button_attr=button_attr)
        return

    close_callback()
