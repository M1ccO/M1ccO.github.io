from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QDialog, QWidget

try:
    from ui.main_window_support import pause_tool_library_preload, resume_tool_library_preload
except Exception:
    pause_tool_library_preload = None
    resume_tool_library_preload = None


def resolve_work_editor_parent(page) -> QWidget | None:
    if not isinstance(page, QWidget):
        return None
    window = page.window()
    if isinstance(window, QWidget):
        return window
    return page


def prime_work_editor_dialog(dialog) -> None:
    if not isinstance(dialog, QDialog):
        return
    if getattr(dialog, "_startup_open_primed", False):
        return

    dialog._startup_open_primed = True
    ensure_polished = getattr(dialog, "ensurePolished", None)
    if callable(ensure_polished):
        ensure_polished()

    app = QApplication.instance()
    if app is not None:
        app.processEvents()

    # Build lazy tabs with updates disabled to avoid focus-stealing flashes
    # on Windows during widget construction.
    dialog.setUpdatesEnabled(False)
    try:
        close_popups = getattr(dialog, "_close_transient_combo_popups", None)
        if callable(close_popups):
            close_popups()
    finally:
        dialog.setUpdatesEnabled(True)

    if app is not None:
        app.processEvents()


def _position_dialog_over_host(dialog, host: QWidget | None) -> None:
    if not isinstance(dialog, QDialog) or not isinstance(host, QWidget) or not host.isVisible():
        return
    _position_dialog_from_geometry(dialog, host.frameGeometry())


def _position_dialog_from_geometry(dialog, host_geometry: QRect | None) -> None:
    if not isinstance(dialog, QDialog) or not isinstance(host_geometry, QRect):
        return
    dialog_size = dialog.size()
    if not dialog_size.isValid():
        dialog_size = dialog.sizeHint()
    if not dialog_size.isValid():
        return
    x = host_geometry.x() + max(0, (host_geometry.width() - dialog_size.width()) // 2)
    y = host_geometry.y() + max(0, (host_geometry.height() - dialog_size.height()) // 2)
    dialog.move(x, y)


def exec_work_editor_dialog(dialog) -> int:
    parent_widget_fn = getattr(dialog, "parentWidget", None)
    parent_widget = parent_widget_fn() if callable(parent_widget_fn) else None
    explicit_host = getattr(dialog, "_explicit_style_host", None)
    preload_host = explicit_host if isinstance(explicit_host, QWidget) else None
    if preload_host is None and isinstance(parent_widget, QWidget):
        preload_host = parent_widget.window()
    host_geometry = None
    if isinstance(preload_host, QWidget):
        host_geometry = preload_host.frameGeometry()
    begin_trace = getattr(preload_host, "_begin_modal_trace", None)
    if callable(begin_trace):
        begin_trace(
            "work_editor_exec",
            dialog_class=type(dialog).__name__,
            host_visible=bool(isinstance(preload_host, QWidget) and preload_host.isVisible()),
            host_active=bool(isinstance(preload_host, QWidget) and preload_host.isActiveWindow()),
        )
    if callable(pause_tool_library_preload) and isinstance(preload_host, QWidget):
        pause_tool_library_preload(preload_host)
    trace_event = getattr(preload_host, "_trace_modal_event", None)
    prime_work_editor_dialog(dialog)
    if isinstance(host_geometry, QRect):
        _position_dialog_from_geometry(dialog, host_geometry)
    else:
        _position_dialog_over_host(dialog, preload_host)
    if callable(trace_event):
        trace_event("pre_exec", dialog_visible=bool(getattr(dialog, "isVisible", lambda: False)()))
    try:
        result = dialog.exec()
        if callable(trace_event):
            trace_event("post_exec", result=result)
        return result
    finally:
        if callable(resume_tool_library_preload) and isinstance(preload_host, QWidget):
            resume_tool_library_preload(preload_host, schedule_delay_ms=1800)
        end_trace = getattr(preload_host, "_end_modal_trace", None)
        if callable(end_trace):
            end_trace(
                "work_editor_exec_complete",
                host_visible=bool(isinstance(preload_host, QWidget) and preload_host.isVisible()),
                host_active=bool(isinstance(preload_host, QWidget) and preload_host.isActiveWindow()),
            )
