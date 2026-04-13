"""Shared detached-preview shell helpers used by TOOLS and JAWS pages."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QKeySequence, QShortcut


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
    """Position detached preview dialog relative to host window geometry."""
    dialog = getattr(page, dialog_attr, None)
    if dialog is None:
        return

    host_window = page.window()
    if host_window is None:
        return

    host_frame = host_window.frameGeometry()
    if host_frame.width() <= 0 or host_frame.height() <= 0:
        return

    width = min(max(520, int(host_frame.width() * 0.37)), 700)
    max_height = max(420, host_frame.height() - 30)
    height = min(max(600, int(host_frame.height() * 0.86)), max_height)

    x = host_frame.right() - width + 1
    y = max(host_frame.top() + 30, host_frame.bottom() - height + 1)
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
