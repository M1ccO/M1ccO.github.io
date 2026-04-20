from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from ui.preferences_dialog import PreferencesDialog
from .library_handoff_controller import _show_library_start_timeout
from .library_ipc import allow_set_foreground


def _trigger_library_import_export(window, library: str, command: str) -> None:
    """Send an open_import_dialog / open_export_dialog IPC command to Library.

    Auto-launches Library if it is not already running.
    """
    allow_set_foreground()
    payload = {
        "command": command,
        "library": library,
        "show": True,
        "tools_db_path": str(getattr(window.draw_service, "tool_db_path", "")),
        "jaws_db_path": str(getattr(window.draw_service, "jaw_db_path", "")),
        "fixtures_db_path": str(getattr(window.draw_service, "fixture_db_path", "")),
    }
    if window._send_to_tool_library(payload):
        return
    if window._launch_tool_library([]):
        window._send_request_with_retry(
            payload,
            on_failed=lambda: _show_library_start_timeout(window),
        )


def open_preferences_action(window) -> None:
    dialog = PreferencesDialog(
        window.ui_preferences,
        window._t,
        parent=window,
        machine_config_svc=getattr(window, "machine_config_svc", None),
        on_import_clicked=lambda lib: _trigger_library_import_export(window, lib, "open_import_dialog"),
        on_export_clicked=lambda lib: _trigger_library_import_export(window, lib, "open_export_dialog"),
    )
    result = dialog.exec()

    # ----------------------------------------------------------------
    # Live configuration switch (dropdown change, Edit with reload, New)
    #
    # The dialog stores the target config_id in _pending_switch_config_id
    # and closes via reject() so we can intercept here before touching
    # any other preferences.
    # ----------------------------------------------------------------
    pending_id = getattr(dialog, "_pending_switch_config_id", None)
    if pending_id:
        window.config_switch_requested.emit(pending_id)
        return

    if result != PreferencesDialog.Accepted:
        return

    # ----------------------------------------------------------------
    # Normal Save — language, theme, model paths, DB path, etc.
    # ----------------------------------------------------------------
    previous_language = window.ui_preferences.get("language", "en")
    # Carry the DB-bound machine_profile_key forward so save() does not
    # overwrite it with the UiPreferencesService default.
    payload = dialog.preferences_payload()
    payload["machine_profile_key"] = window.ui_preferences.get(
        "machine_profile_key", "ntx_2sp_2h"
    )

    window.ui_preferences = window.ui_preferences_service.save(payload)
    window.localization.set_language(window.ui_preferences.get("language", "en"))
    if hasattr(window.print_service, "set_translator"):
        window.print_service.set_translator(window._t)
    window._apply_style()
    window._refresh_localized_labels()

    # If currently on drawings page and it was just disabled, switch away.
    if (
        window.stack.currentIndex() == 1
        and not window.ui_preferences.get("enable_drawings_tab", True)
    ):
        window._set_page(0)
    window.setup_page.drawings_enabled = window.ui_preferences.get(
        "enable_drawings_tab", True
    )

    QMessageBox.information(
        window,
        window._t("preferences.saved_title", "Preferences"),
        window._t("preferences.saved_body", "Preferences saved."),
    )
    if window.ui_preferences.get("language", "en") != previous_language:
        QMessageBox.information(
            window,
            window._t("preferences.restart_title", "Restart Required"),
            window._t(
                "preferences.restart_body",
                "Language changes will be applied after restarting the app.",
            ),
        )
