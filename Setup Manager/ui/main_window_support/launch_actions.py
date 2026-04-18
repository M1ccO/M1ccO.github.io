from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from ui.machine_family_runtime import secondary_library_label, secondary_library_module


def set_launch_button_variant(window, button, primary: bool) -> None:
    button.setProperty("primaryAction", bool(primary))
    button.setProperty("secondaryAction", not bool(primary))
    button.style().unpolish(button)
    button.style().polish(button)


def on_setup_launch_context_changed(window, context) -> None:
    window._launch_context = dict(context or {})
    update_launch_actions(window)


def update_navigation_labels(window) -> None:
    drawings_enabled = window.ui_preferences.get("enable_drawings_tab", True)
    for idx, button in enumerate(getattr(window, "nav_buttons", [])):
        if idx == 0:
            text = window._t("setup_manager.nav.setups", "SETUPS")
            button.setVisible(True)
        elif idx == 1:
            key = "setup_manager.nav.show_drawing" if window._launch_context.get("selected") else "setup_manager.nav.drawings"
            default = "SHOW DRAWING" if window._launch_context.get("selected") else "DRAWINGS"
            text = window._t(key, default)
            button.setVisible(drawings_enabled)
            button.setEnabled(drawings_enabled)
            button.setToolTip("" if drawings_enabled else window._t("preferences.drawings_tab_disabled_hint", "Drawings tab is disabled in Preferences."))
        else:
            text = window._t("setup_manager.nav.logbook", "LOGBOOK")
            button.setVisible(True)
        button.setText(text)


def update_launch_actions(window) -> None:
    selected = bool(window._launch_context.get("selected"))
    secondary_module = secondary_library_module(
        profile_key=getattr(window.work_service, "get_machine_profile_key", lambda: None)()
    )
    secondary_label = secondary_library_label(
        profile_key=getattr(window.work_service, "get_machine_profile_key", lambda: None)()
    )
    if hasattr(window, "open_jaws_btn"):
        if secondary_module == "fixtures":
            window.open_jaws_btn.setText(
                window._t("setup_manager.open_fixtures_library", "Open Fixtures Library")
            )
        else:
            window.open_jaws_btn.setText(
                window._t("setup_manager.open_jaws_library", "Open Jaws Library")
            )
    update_navigation_labels(window)
    if selected:
        # Selected-work mode: make launch actions clearly contextual and emphasize
        # filtered opening behavior.
        work_id = str(window._launch_context.get("work_id") or "").strip()
        window.launch_body.setText(
            window._t(
                "setup_manager.launch.selected_body",
                "Selected work {work_id}: open filtered Tool Library and {secondary_label} Library views.",
                work_id=work_id,
                secondary_label=secondary_label,
            )
            if work_id
            else window._t(
                "setup_manager.launch.selected_body_no_id",
                "Selected work: open filtered Tool Library and {secondary_label} Library views.",
                secondary_label=secondary_label,
            )
        )
        set_launch_button_variant(window, window.open_tools_btn, True)
        set_launch_button_variant(window, window.open_jaws_btn, True)
    else:
        # Default mode: no selected setup context, so actions open unfiltered views.
        window.launch_body.setText(
            window._t(
                "setup_manager.launch.default_body",
                "Open Tool Library or {secondary_label} Library. Select a work in Setup to open filtered data.",
                secondary_label=secondary_label,
            )
        )
        set_launch_button_variant(window, window.open_tools_btn, False)
        set_launch_button_variant(window, window.open_jaws_btn, False)


def open_tool_library_action(window) -> None:
    if window._launch_context.get("selected"):
        if not window._launch_context.get("has_data"):
            QMessageBox.information(
                window,
                window._t("setup_manager.viewer.title", "Viewer"),
                window._t("setup_manager.viewer.no_links", "No jaw/tool links were found for this setup."),
            )
            return
        window._open_tool_library_with_master_filter(
            window._launch_context.get("tool_ids") or [],
            window._launch_context.get("jaw_ids") or [],
            module="tools",
        )
        return
    window._open_tool_library_module("tools")


def open_jaws_library_action(window) -> None:
    secondary_module = secondary_library_module(
        profile_key=getattr(window.work_service, "get_machine_profile_key", lambda: None)()
    )
    if window._launch_context.get("selected"):
        tool_ids = window._launch_context.get("tool_ids") or []
        jaw_ids = window._launch_context.get("jaw_ids") or []
        if not jaw_ids and secondary_module != "fixtures":
            QMessageBox.information(
                window,
                window._t("setup_manager.viewer.title", "Viewer"),
                window._t("setup_manager.viewer.no_jaws", "No jaws selected for this work."),
            )
            return
        window._open_tool_library_with_master_filter(tool_ids, jaw_ids, module=secondary_module)
        return
    window._open_tool_library_module(secondary_module)
