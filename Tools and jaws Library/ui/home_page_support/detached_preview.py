"""Detached 3D preview dialog management for HomePage."""

from __future__ import annotations

import json

from PySide6.QtWidgets import QMessageBox

from config import TOOL_ICONS_DIR
from shared.ui.helpers.detached_preview_common import (
    set_preview_button_checked as _set_preview_button_checked,
    toggle_preview_window as _toggle_preview_window,
    update_measurement_toggle_icon,
)
from ui.selectors.external_preview_host import close_preview_host, show_preview_host


_STATE_PREFIX = "_detached_preview"
_GEOMETRY_KEY = "tool_detached_preview_dialog"


def load_preview_content(viewer, stl_path: str | None, label: str | None = None) -> bool:
    if viewer is None or not stl_path:
        return False

    try:
        parsed = json.loads(stl_path)
        if isinstance(parsed, list):
            viewer.load_parts(parsed)
            return True
        if isinstance(parsed, str) and parsed.strip():
            viewer.load_stl(parsed, label=label)
            return True
    except Exception:
        viewer.load_stl(stl_path, label=label)
        return True

    return False


def set_preview_button_checked(page, checked: bool):
    _set_preview_button_checked(page, checked)


def update_detached_measurement_toggle_icon(page, enabled: bool):
    update_measurement_toggle_icon(
        page,
        bool(enabled),
        icons_dir=TOOL_ICONS_DIR,
        translate=page._t,
        hide_key="tool_library.preview.measurements_hide",
        show_key="tool_library.preview.measurements_show",
        hide_default="Piilota mittaukset",
        show_default="Nayta mittaukset",
    )


def on_detached_measurements_toggled(page, checked: bool):
    page._detached_measurements_enabled = bool(checked)
    update_detached_measurement_toggle_icon(page, page._detached_measurements_enabled)
    viewer = getattr(page, "_detached_preview_widget", None)
    if viewer is not None:
        viewer.set_measurements_visible(page._detached_measurements_enabled)


def apply_detached_measurement_state(page, overlays):
    if page._detached_preview_widget is None:
        return
    page._detached_preview_widget.set_measurement_overlays(overlays or [])
    page._detached_preview_widget.set_measurements_visible(bool(overlays) and page._detached_measurements_enabled)
    page._detached_preview_widget.set_measurement_filter(getattr(page, "_detached_measurement_filter", None))


def _on_preview_host_finished(page) -> None:
    page._measurement_toggle_btn = None
    page._measurement_filter_combo = None
    page._detached_preview_last_model_key = None
    page._detached_preview_pending_show = False
    set_preview_button_checked(page, False)


def ensure_detached_preview_dialog(page):
    if getattr(page, "_detached_preview_dialog", None) is not None:
        return
    sync_detached_preview(page, show_errors=False)


def apply_detached_preview_default_bounds(page):
    _ = page


def on_detached_preview_closed(page):
    _on_preview_host_finished(page)


def refresh_detached_measurement_controls(page, overlays):
    button = getattr(page, "_measurement_toggle_btn", None)
    if button is None:
        return
    has_measurements = bool(overlays)
    button.setEnabled(has_measurements)
    button.blockSignals(True)
    button.setChecked(page._detached_measurements_enabled and has_measurements)
    button.blockSignals(False)
    update_detached_measurement_toggle_icon(page, button.isChecked())
    page._detached_measurement_filter = None


def _build_preview_payload(page, tool: dict) -> dict:
    stl_path = tool.get("stl_path")
    label = tool.get("description", "").strip() or tool.get("id", "3D Preview")
    raw_model_key = stl_path if isinstance(stl_path, str) else json.dumps(stl_path, ensure_ascii=False, sort_keys=True)
    model_key = (
        int(tool.get("uid")) if str(tool.get("uid", "")).strip().isdigit() else str(tool.get("id") or "").strip(),
        str(raw_model_key or ""),
    )
    overlays = tool.get("measurement_overlays", []) if isinstance(tool, dict) else []
    tool_id = page._tool_id_display_value(tool.get("id", ""))
    payload = {
        "model_key": model_key,
        "label": label,
        "title": page._t("tool_library.preview.window_title_tool", "3D Preview - {tool_id}", tool_id=tool_id).rstrip(" -"),
        "measurement_overlays": overlays if isinstance(overlays, list) else [],
    }
    if isinstance(stl_path, str):
        try:
            parsed = json.loads(stl_path)
            if isinstance(parsed, list):
                payload["parts"] = parsed
            elif isinstance(parsed, str) and parsed.strip():
                payload["stl_path"] = parsed
            else:
                payload["stl_path"] = stl_path
        except Exception:
            payload["stl_path"] = stl_path
    elif isinstance(stl_path, list):
        payload["parts"] = [dict(item) for item in stl_path if isinstance(item, dict)]
    return payload


def close_detached_preview(page):
    close_preview_host(page, state_prefix=_STATE_PREFIX)


def sync_detached_preview(page, show_errors: bool = False) -> bool:
    if not page.preview_window_btn.isChecked():
        return False

    dialog_visible = bool(page._detached_preview_dialog and page._detached_preview_dialog.isVisible())
    if not page.current_tool_id:
        if dialog_visible and not show_errors:
            return False
        close_detached_preview(page)
        return False

    tool = page._get_selected_tool()
    if not tool:
        if dialog_visible and not show_errors:
            return False
        close_detached_preview(page)
        return False

    stl_path = tool.get("stl_path")
    if not stl_path:
        if show_errors:
            QMessageBox.information(
                page,
                page._t("tool_library.preview.window_title", "3D Preview"),
                page._t("tool_library.preview.none_assigned_selected", "The selected tool has no 3D model assigned."),
            )
        if dialog_visible and not show_errors:
            return False
        close_detached_preview(page)
        return False

    payload = _build_preview_payload(page, tool)
    if not show_preview_host(
        page,
        payload,
        state_prefix=_STATE_PREFIX,
        geometry_key=_GEOMETRY_KEY,
        measurement_button_attr="_measurement_toggle_btn",
        measurements_enabled_attr="_detached_measurements_enabled",
        close_shortcut_attr="_close_preview_shortcut",
        on_finished_callback=_on_preview_host_finished,
    ):
        close_detached_preview(page)
        return False

    refresh_detached_measurement_controls(page, payload.get("measurement_overlays", []))
    apply_detached_measurement_state(page, payload.get("measurement_overlays", []))
    set_preview_button_checked(page, True)
    return True


def toggle_preview_window(page):
    _toggle_preview_window(
        page,
        sync_callback=lambda show_errors: sync_detached_preview(page, show_errors=show_errors),
        close_callback=lambda: close_detached_preview(page),
    )
