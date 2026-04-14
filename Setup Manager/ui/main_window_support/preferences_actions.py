from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from ui.preferences_dialog import PreferencesDialog


def open_preferences_action(window) -> None:
    dialog = PreferencesDialog(
        window.ui_preferences,
        window._t,
        parent=window,
        active_db_path=str(getattr(window.work_service.db, "path", "") or ""),
        on_check_compatibility=window._check_setup_db_compatibility,
    )
    if dialog.exec() != PreferencesDialog.Accepted:
        return

    previous_language = window.ui_preferences.get("language", "en")
    previous_setup_db = str(window.ui_preferences.get("setup_db_path", "") or "").strip()
    window.ui_preferences = window.ui_preferences_service.save(dialog.preferences_payload())
    window.localization.set_language(window.ui_preferences.get("language", "en"))
    if hasattr(window.print_service, "set_translator"):
        window.print_service.set_translator(window._t)
    window._apply_style()
    window._refresh_localized_labels()

    # If currently on drawings page and it was just disabled, switch away.
    if window.stack.currentIndex() == 1 and not window.ui_preferences.get("enable_drawings_tab", True):
        window._set_page(0)
    window.setup_page.drawings_enabled = window.ui_preferences.get("enable_drawings_tab", True)

    QMessageBox.information(
        window,
        window._t("preferences.saved_title", "Preferences"),
        window._t("preferences.saved_body", "Preferences saved."),
    )
    if window.ui_preferences.get("language", "en") != previous_language:
        QMessageBox.information(
            window,
            window._t("preferences.restart_title", "Restart Required"),
            window._t("preferences.restart_body", "Language changes will be applied after restarting the app."),
        )
    current_setup_db = str(window.ui_preferences.get("setup_db_path", "") or "").strip()
    if current_setup_db != previous_setup_db:
        QMessageBox.information(
            window,
            window._t("preferences.restart_title", "Restart Required"),
            window._t(
                "preferences.restart_db_body",
                "Database path changes will be applied after restarting the app.",
            ),
        )
