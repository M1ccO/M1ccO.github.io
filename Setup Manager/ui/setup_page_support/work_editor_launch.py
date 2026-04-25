from __future__ import annotations

import os
import time

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QDialog, QGraphicsBlurEffect, QWidget

from shared.ui.main_window_helpers import exec_dialog_with_blur, prime_dialog

try:
    from ui.main_window_support import pause_tool_library_preload, resume_tool_library_preload
except Exception:
    pause_tool_library_preload = None
    resume_tool_library_preload = None

_ENABLE_WORK_EDITOR_HOST_BLUR = str(
    os.environ.get("NTX_ENABLE_WORK_EDITOR_HOST_BLUR", "1")
).strip().lower() in {"1", "true", "yes", "on"}


def pause_preload_before_work_editor_launch(host: QWidget | None) -> bool:
    """Pause hidden Tool Library preload for the full Work Editor launch path.

    Returns True when a pause token was acquired and the caller must resume it.
    """
    if callable(pause_tool_library_preload) and isinstance(host, QWidget):
        pause_tool_library_preload(host)
        return True
    return False


def resume_preload_after_work_editor_launch(host: QWidget | None, *, schedule_delay_ms: int = 1800) -> None:
    """Release one preload pause token acquired before Work Editor launch."""
    if callable(resume_tool_library_preload) and isinstance(host, QWidget):
        resume_tool_library_preload(host, schedule_delay_ms=schedule_delay_ms)


def resolve_work_editor_parent(page) -> QWidget | None:
    if not isinstance(page, QWidget):
        return None
    window = page.window()
    if isinstance(window, QWidget):
        return window
    return page


def prime_work_editor_dialog(dialog) -> None:
    """Specialized priming for Work Editor, delegating to shared prime_dialog."""
    if not isinstance(dialog, QDialog):
        return
    if getattr(dialog, "_startup_open_primed", False):
        return
    dialog._startup_open_primed = True

    # Shared priming (polished, updates disabled, layout activate) - includes standard hooks
    prime_dialog(dialog)

    # Additional work-editor-specific hooks NOT in prime_dialog's standard list
    for hook in (
        "_close_transient_combo_popups",
    ):
        method = getattr(dialog, hook, None)
        if callable(method):
            try:
                method()
            except Exception:
                pass


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

    # Prime layout/style
    prime_dialog(dialog)

    # Position dialog centered over the host
    if isinstance(preload_host, QWidget) and preload_host.isVisible():
        host_geom = preload_host.frameGeometry()
        dlg_size = dialog.size()
        if not dlg_size.isValid():
            dlg_size = dialog.sizeHint()
        if dlg_size.isValid():
            x = host_geom.x() + max(0, (host_geom.width() - dlg_size.width()) // 2)
            y = host_geom.y() + max(0, (host_geom.height() - dlg_size.height()) // 2)
            dialog.move(x, y)

    if callable(trace_event):
        trace_event("pre_exec", dialog_visible=bool(getattr(dialog, "isVisible", lambda: False)()))

    # Blur the main window while the Work Editor is open.
    _blur_effect = None
    if _ENABLE_WORK_EDITOR_HOST_BLUR and isinstance(preload_host, QWidget) and preload_host.isVisible():
        try:
            _blur_effect = QGraphicsBlurEffect(preload_host)
            _blur_effect.setBlurRadius(6)
            preload_host.setGraphicsEffect(_blur_effect)
        except Exception:
            _blur_effect = None

    try:
        # We use dialog.exec() directly here because work_editor has specialized
        # post-exec loop logic (IPC selector wait) that we don't want to break.
        result = dialog.exec()

        _app = QApplication.instance()
        if _app is not None:
            _app.processEvents()

        _needs_extended_wait = isinstance(dialog, QDialog) and (
            getattr(getattr(dialog, "_selector_ctrl", None), "_pending_ipc_request_id", None) is not None
            or dialog.isVisible()
        )
        if _needs_extended_wait:
            wait_started_at = time.monotonic()
            heartbeat_deadline = wait_started_at + 1.0
            while True:
                try:
                    ipc_pending = getattr(getattr(dialog, "_selector_ctrl", None), "_pending_ipc_request_id", None) is not None
                    dialog_visible = dialog.isVisible()
                except RuntimeError:
                    break
                if not ipc_pending and not dialog_visible:
                    break
                if _app is None:
                    break
                _app.processEvents()
                if time.monotonic() >= heartbeat_deadline:
                    heartbeat_deadline = time.monotonic() + 1.0
                    if callable(trace_event):
                        trace_event(
                            "ipc_selector_wait",
                            elapsed_ms=int((time.monotonic() - wait_started_at) * 1000),
                            ipc_pending=ipc_pending,
                            dialog_visible=dialog_visible,
                        )

            try:
                result = int(getattr(dialog, "result", lambda: result)())
            except RuntimeError:
                pass

        if callable(trace_event):
            trace_event("post_exec", result=result)
        return result
    finally:
        if _blur_effect is not None and isinstance(preload_host, QWidget):
            try:
                preload_host.setGraphicsEffect(None)
            except Exception:
                pass

        if callable(resume_tool_library_preload) and isinstance(preload_host, QWidget):
            dialog_still_visible = False
            try:
                dialog_still_visible = bool(isinstance(dialog, QDialog) and dialog.isVisible())
            except RuntimeError:
                dialog_still_visible = False
            if not dialog_still_visible:
                resume_tool_library_preload(preload_host, schedule_delay_ms=1800)
            elif callable(trace_event):
                trace_event("resume_preload_skipped_dialog_visible")
        end_trace = getattr(preload_host, "_end_modal_trace", None)
        if callable(end_trace):
            end_trace(
                "work_editor_exec_complete",
                host_visible=bool(isinstance(preload_host, QWidget) and preload_host.isVisible()),
                host_active=bool(isinstance(preload_host, QWidget) and preload_host.isActiveWindow()),
            )
