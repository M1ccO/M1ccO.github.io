from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication


def _is_visible_work_editor(widget) -> bool:
    return bool(widget is not None and widget.isVisible() and widget.property("workEditorDialog"))


def initialize_preload_state(window) -> None:
    window._tool_library_preload_completed = False
    window._tool_library_preload_retries = 0
    window._tool_library_preload_max_retries = 24
    window._tool_library_preload_scheduled = False
    window._tool_library_preload_pause_count = 0
    window._tool_library_preload_launch_started = False


def pause_tool_library_preload(window) -> None:
    window._tool_library_preload_pause_count = max(0, int(getattr(window, "_tool_library_preload_pause_count", 0))) + 1


def resume_tool_library_preload(window, schedule_delay_ms: int = 700) -> None:
    pause_count = max(0, int(getattr(window, "_tool_library_preload_pause_count", 0)))
    if pause_count <= 0:
        return
    window._tool_library_preload_pause_count = pause_count - 1
    if window._tool_library_preload_pause_count == 0 and not getattr(window, "_tool_library_preload_completed", False):
        if not getattr(window, "_tool_library_preload_scheduled", False):
            window._tool_library_preload_scheduled = True
            QTimer.singleShot(max(0, int(schedule_delay_ms)), lambda: retry_tool_library_preload(window))


def preload_tool_library_background(window) -> None:
    if window._tool_library_preload_completed:
        return
    if int(getattr(window, "_tool_library_preload_pause_count", 0)) > 0:
        if not window._tool_library_preload_scheduled:
            window._tool_library_preload_scheduled = True
            QTimer.singleShot(700, lambda: retry_tool_library_preload(window))
        return

    app = QApplication.instance()
    active_modal = app.activeModalWidget() if app is not None else None
    work_editor_visible = False
    if app is not None:
        for top in app.topLevelWidgets():
            if _is_visible_work_editor(top):
                work_editor_visible = True
                break

    if (
        active_modal is not None
        or work_editor_visible
        or not window.isVisible()
        or window.isMinimized()
    ):
        if window._tool_library_preload_retries < window._tool_library_preload_max_retries:
            window._tool_library_preload_retries += 1
            if not window._tool_library_preload_scheduled:
                window._tool_library_preload_scheduled = True
                QTimer.singleShot(700, lambda: retry_tool_library_preload(window))
        return

    if window._send_to_tool_library({"show": False}):
        window._tool_library_preload_completed = True
        window._tool_library_preload_launch_started = False
        return

    launch_started = bool(getattr(window, "_tool_library_preload_launch_started", False))
    ready_check = getattr(window, "_is_tool_library_ready", None)
    is_ready = False
    if callable(ready_check):
        try:
            is_ready = bool(ready_check())
        except Exception:
            is_ready = False

    if launch_started or is_ready:
        if window._tool_library_preload_retries < window._tool_library_preload_max_retries:
            window._tool_library_preload_retries += 1
            if not window._tool_library_preload_scheduled:
                window._tool_library_preload_scheduled = True
                QTimer.singleShot(350, lambda: retry_tool_library_preload(window))
        return

    if window._launch_tool_library(["--hidden"]):
        window._tool_library_preload_launch_started = True
        if not window._tool_library_preload_scheduled:
            window._tool_library_preload_scheduled = True
            QTimer.singleShot(350, lambda: retry_tool_library_preload(window))


def retry_tool_library_preload(window) -> None:
    window._tool_library_preload_scheduled = False
    preload_tool_library_background(window)


