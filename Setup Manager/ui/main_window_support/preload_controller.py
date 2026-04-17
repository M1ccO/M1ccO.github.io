from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

_LOGGER = logging.getLogger(__name__)


def initialize_preload_state(window) -> None:
    window._tool_library_preload_completed = False
    window._tool_library_preload_retries = 0
    window._tool_library_preload_max_retries = 24
    window._tool_library_preload_scheduled = False
    window._tool_library_preload_pause_count = 0
    window._work_editor_preload_completed = False
    window._work_editor_preload_retries = 0
    window._work_editor_preload_max_retries = 18
    window._work_editor_preload_scheduled = False
    window._work_editor_preload_dialog = None


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
            if top.__class__.__name__ == "WorkEditorDialog" and top.isVisible():
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
        return

    if window._launch_tool_library(["--hidden"]):
        window._tool_library_preload_completed = True


def retry_tool_library_preload(window) -> None:
    window._tool_library_preload_scheduled = False
    preload_tool_library_background(window)


def preload_work_editor_background(window) -> None:
    if bool(getattr(window, "_work_editor_preload_completed", False)):
        return

    app = QApplication.instance()
    active_modal = app.activeModalWidget() if app is not None else None
    work_editor_visible = False
    if app is not None:
        for top in app.topLevelWidgets():
            if top.__class__.__name__ == "WorkEditorDialog" and top.isVisible():
                work_editor_visible = True
                break

    if (
        active_modal is not None
        or work_editor_visible
        or not window.isVisible()
        or window.isMinimized()
    ):
        if int(getattr(window, "_work_editor_preload_retries", 0)) < int(getattr(window, "_work_editor_preload_max_retries", 18)):
            window._work_editor_preload_retries = int(getattr(window, "_work_editor_preload_retries", 0)) + 1
            if not bool(getattr(window, "_work_editor_preload_scheduled", False)):
                window._work_editor_preload_scheduled = True
                QTimer.singleShot(700, lambda: retry_work_editor_preload(window))
        return

    try:
        from ui.work_editor_dialog import WorkEditorDialog
    except Exception:
        _LOGGER.exception("work_editor_preload: failed to import WorkEditorDialog")
        return

    try:
        machine_profile_key = None
        if hasattr(window, "work_service") and hasattr(window.work_service, "get_machine_profile_key"):
            machine_profile_key = window.work_service.get_machine_profile_key()

        drawings_enabled = True
        setup_page = getattr(window, "setup_page", None)
        if setup_page is not None:
            drawings_enabled = bool(getattr(setup_page, "drawings_enabled", True))

        dialog = WorkEditorDialog(
            getattr(window, "draw_service", None),
            parent=None,
            style_host=window,
            translate=getattr(window, "_t", None),
            drawings_enabled=drawings_enabled,
            machine_profile_key=machine_profile_key,
        )

        # Prevent focus-stealing flash during background preload.
        dialog.setAttribute(Qt.WA_DontShowOnScreen, True)
        dialog.setAttribute(Qt.WA_ShowWithoutActivating, True)
        dialog.setUpdatesEnabled(False)

        try:
            ensure_polished = getattr(dialog, "ensurePolished", None)
            if callable(ensure_polished):
                ensure_polished()

            if app is not None:
                app.processEvents()

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

            if app is not None:
                app.processEvents()
        finally:
            dialog.setAttribute(Qt.WA_DontShowOnScreen, False)
            dialog.setAttribute(Qt.WA_ShowWithoutActivating, False)
            dialog.setUpdatesEnabled(True)

        dialog.hide()
        window._work_editor_preload_dialog = dialog
        window._work_editor_preload_completed = True
    except Exception:
        _LOGGER.exception("work_editor_preload: failed to initialize hidden preloaded editor")


def retry_work_editor_preload(window) -> None:
    window._work_editor_preload_scheduled = False
    preload_work_editor_background(window)
