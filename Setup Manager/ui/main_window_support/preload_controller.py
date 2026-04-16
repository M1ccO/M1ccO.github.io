from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication


def initialize_preload_state(window) -> None:
    window._tool_library_preload_completed = False
    window._tool_library_preload_retries = 0
    window._tool_library_preload_max_retries = 24
    window._tool_library_preload_scheduled = False


def preload_tool_library_background(window) -> None:
    if window._tool_library_preload_completed:
        return

    app = QApplication.instance()
    active_modal = app.activeModalWidget() if app is not None else None
    if active_modal is not None or not window.isVisible() or window.isMinimized():
        if window._tool_library_preload_retries < window._tool_library_preload_max_retries:
            window._tool_library_preload_retries += 1
            if not window._tool_library_preload_scheduled:
                window._tool_library_preload_scheduled = True
                QTimer.singleShot(700, lambda: retry_tool_library_preload(window))
        return

    if window._send_to_tool_library({"show": False}):
        window._tool_library_preload_completed = True
        return

    if window._launch_tool_library(["--hidden"]):
        window._tool_library_preload_completed = True


def retry_tool_library_preload(window) -> None:
    window._tool_library_preload_scheduled = False
    preload_tool_library_background(window)
