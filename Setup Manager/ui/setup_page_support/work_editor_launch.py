from __future__ import annotations

import time

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QDialog, QGraphicsBlurEffect, QWidget

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
        activate_layout = getattr(dialog.layout(), "activate", None)
        if callable(activate_layout):
            activate_layout()

        ensure_surface = getattr(dialog, "_ensure_normal_editor_surface_visible", None)
        if callable(ensure_surface):
            ensure_surface()

        ensure_content = getattr(dialog, "_ensure_normal_editor_content_visible", None)
        if callable(ensure_content):
            ensure_content()

        warmup_surfaces = getattr(dialog, "_warmup_initial_interaction_surfaces", None)
        if callable(warmup_surfaces):
            warmup_surfaces()

        close_popups = getattr(dialog, "_close_transient_combo_popups", None)
        if callable(close_popups):
            close_popups()

        update_geometry = getattr(dialog, "updateGeometry", None)
        if callable(update_geometry):
            update_geometry()
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

    def _wait_for_real_close(previous_result: int) -> int:
        """Keep the editor modal when Qt drops out of exec() too early.

        Tool Selector can currently cause a premature exec() return even though the
        Work Editor dialog is still visible and interactive. In that case we must
        not let the caller resume as if the dialog really closed.
        """
        if not isinstance(dialog, QDialog):
            return previous_result
        if not dialog.isVisible():
            return previous_result

        _ctrl = getattr(dialog, "_selector_ctrl", None)
        selector_active = bool(getattr(_ctrl, "mode_active", False)) if _ctrl is not None else False
        host = getattr(dialog, "_embedded_selector_host", None)
        host_widget = getattr(host, "active_widget", None) if host is not None else None
        if callable(trace_event):
            trace_event(
                "spurious_exec_return",
                result=previous_result,
                dialog_visible=True,
                selector_active=selector_active,
                active_selector_widget=type(host_widget).__name__ if host_widget is not None else "",
            )
        app = QApplication.instance()
        if app is None:
            if callable(trace_event):
                trace_event("spurious_exec_return_no_app")
            return previous_result

        wait_started_at = time.monotonic()
        heartbeat_deadline = wait_started_at + 1.0
        while True:
            try:
                if not dialog.isVisible():
                    break
            except RuntimeError:
                break

            app.processEvents()
            if time.monotonic() >= heartbeat_deadline:
                heartbeat_deadline = time.monotonic() + 1.0
                if callable(trace_event):
                    trace_event(
                        "spurious_exec_return_waiting",
                        elapsed_ms=int((time.monotonic() - wait_started_at) * 1000),
                        dialog_visible=bool(getattr(dialog, "isVisible", lambda: False)()),
                        selector_active=bool(getattr(getattr(dialog, "_selector_ctrl", None), "mode_active", False)),
                    )

        try:
            final_result = int(getattr(dialog, "result", lambda: previous_result)())
        except RuntimeError:
            final_result = previous_result
        if callable(trace_event):
            trace_event(
                "spurious_exec_return_resolved",
                previous_result=previous_result,
                final_result=final_result,
                dialog_visible=bool(getattr(dialog, "isVisible", lambda: False)()),
            )
        return final_result

    # Blur the main window while the Work Editor is open.
    _blur_effect = None
    if isinstance(preload_host, QWidget) and preload_host.isVisible():
        try:
            _blur_effect = QGraphicsBlurEffect(preload_host)
            _blur_effect.setBlurRadius(6)
            preload_host.setGraphicsEffect(_blur_effect)
        except Exception:
            _blur_effect = None

    try:
        result = dialog.exec()

        # IPC selector path: dialog hides itself while waiting for the Library
        # process to send back a result.  exec() returns prematurely (Rejected)
        # because Qt drops out of the event loop when the dialog is hidden.
        # We must keep processing events until either:
        #   (a) the IPC result arrives, the dialog shows again, and the user
        #       clicks Save/Cancel (dialog becomes invisible again), or
        #   (b) the pending request is cleared by a cancel or failure path.
        # For the plain close path (no IPC pending, dialog already hidden), this
        # loop exits immediately after the first processEvents() call.
        # For the embedded selector path (dialog still visible), the loop also
        # handles the spurious exec() return case (_wait_for_real_close behaviour).
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
