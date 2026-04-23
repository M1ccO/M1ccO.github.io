from __future__ import annotations

import json

from PySide6.QtWidgets import QMessageBox

from config import TOOL_ICONS_DIR
from shared.ui.helpers.detached_preview_common import (
    set_preview_button_checked as _set_preview_button_checked,
    toggle_preview_window as _toggle_preview_window,
    update_measurement_toggle_icon,
)
from ui.fixture_preview_rules import (
    fixture_preview_has_model_payload,
    fixture_preview_label,
    fixture_preview_measurement_overlays,
    fixture_preview_parts_payload,
    fixture_preview_plane,
    fixture_preview_rotation,
    fixture_preview_stl_path,
)
from ui.jaw_page_support.preview_rules import (
    jaw_preview_has_model_payload,
    jaw_preview_label,
    jaw_preview_measurement_overlays,
    jaw_preview_parts_payload,
    jaw_preview_plane,
    jaw_preview_rotation,
    jaw_preview_stl_path,
)
from ui.selectors.external_preview_host import close_preview_host, show_preview_host


_STATE_PREFIX = "_detached_preview"


def _update_measurement_icon(page, enabled: bool) -> None:
    update_measurement_toggle_icon(
        page,
        bool(enabled),
        icons_dir=TOOL_ICONS_DIR,
        translate=page._t,
        hide_key="tool_library.preview.measurements_hide",
        show_key="tool_library.preview.measurements_show",
        hide_default="Hide measurements",
        show_default="Show measurements",
    )


def _on_host_finished(page) -> None:
    page._measurement_toggle_btn = None
    page._measurement_filter_combo = None
    page._detached_preview_last_model_key = None
    page._detached_preview_pending_show = False
    _set_preview_button_checked(page, False)


def _apply_tool_measurements(page, overlays) -> None:
    if getattr(page, "_detached_preview_widget", None) is None:
        return
    page._detached_preview_widget.set_measurement_overlays(overlays or [])
    page._detached_preview_widget.set_measurements_visible(
        bool(overlays) and bool(getattr(page, "_detached_measurements_enabled", True))
    )
    page._detached_preview_widget.set_measurement_filter(getattr(page, "_detached_measurement_filter", None))
    button = getattr(page, "_measurement_toggle_btn", None)
    if button is not None:
        has_measurements = bool(overlays)
        button.setEnabled(has_measurements)
        button.blockSignals(True)
        button.setChecked(bool(getattr(page, "_detached_measurements_enabled", True)) and has_measurements)
        button.blockSignals(False)
        _update_measurement_icon(page, button.isChecked())


def _apply_domain_measurements(page, overlays) -> None:
    if getattr(page, "_detached_preview_widget", None) is None:
        return
    page._detached_preview_widget.set_measurement_overlays(overlays or [])
    page._detached_preview_widget.set_measurements_visible(
        bool(overlays) and bool(getattr(page, "_detached_measurements_enabled", True))
    )
    button = getattr(page, "_measurement_toggle_btn", None)
    if button is not None:
        button.setEnabled(bool(overlays))
        button.blockSignals(True)
        button.setChecked(bool(getattr(page, "_detached_measurements_enabled", True)) and bool(overlays))
        button.blockSignals(False)
        _update_measurement_icon(page, button.isChecked())


def load_tool_selector_preview_content(viewer, stl_path: str | None, *, label: str | None = None) -> bool:
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


def load_fixture_selector_preview_content(page, viewer, fixture: dict, *, label: str | None = None) -> bool:
    if viewer is None or not isinstance(fixture, dict):
        return False
    parts = fixture_preview_parts_payload(fixture)
    if parts:
        viewer.load_parts(parts)
        return True
    stl_path = fixture_preview_stl_path(fixture)
    if not stl_path:
        return False
    viewer.load_stl(stl_path, label=label or fixture_preview_label(fixture, page._t))
    return True


def load_jaw_selector_preview_content(page, viewer, jaw: dict, *, label: str | None = None) -> bool:
    if viewer is None or not isinstance(jaw, dict):
        return False
    parts = jaw_preview_parts_payload(jaw)
    if parts:
        viewer.load_parts(parts)
        return True
    stl_path = jaw_preview_stl_path(jaw)
    if not stl_path:
        return False
    viewer.load_stl(stl_path, label=label or jaw_preview_label(jaw, page._t))
    return True


def on_tool_selector_detached_measurements_toggled(page, checked: bool) -> None:
    page._detached_measurements_enabled = bool(checked)
    _update_measurement_icon(page, page._detached_measurements_enabled)
    if getattr(page, "_detached_preview_widget", None) is not None:
        page._detached_preview_widget.set_measurements_visible(page._detached_measurements_enabled)


def on_tool_selector_detached_preview_closed(page) -> None:
    _on_host_finished(page)


def _tool_payload(page) -> dict | None:
    tool = getattr(page, "_get_selected_tool", lambda: None)()
    if not tool:
        return None
    stl_path = tool.get("stl_path")
    label = tool.get("description", "").strip() or tool.get("id", "3D Preview")
    raw_model_key = stl_path if isinstance(stl_path, str) else json.dumps(stl_path, ensure_ascii=False, sort_keys=True)
    model_key = (
        int(tool.get("uid")) if str(tool.get("uid", "")).strip().isdigit() else str(tool.get("id") or "").strip(),
        str(raw_model_key or ""),
    )
    payload = {
        "model_key": model_key,
        "label": label,
        "title": page._t(
            "tool_library.preview.window_title_tool",
            "3D Preview - {tool_id}",
            tool_id=str(tool.get("id") or "").strip(),
        ).rstrip(" -"),
        "measurement_overlays": tool.get("measurement_overlays", []) if isinstance(tool.get("measurement_overlays", []), list) else [],
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


def sync_tool_selector_detached_preview(page, show_errors: bool = False) -> bool:
    preview_button = getattr(page, "preview_window_btn", None)
    if preview_button is None or not preview_button.isChecked():
        return False
    dialog_visible = bool(getattr(page, "_detached_preview_dialog", None) and page._detached_preview_dialog.isVisible())
    if not getattr(page, "current_tool_id", None):
        if dialog_visible and not show_errors:
            return False
        close_tool_selector_detached_preview(page)
        return False

    payload = _tool_payload(page)
    has_model = bool(payload and (payload.get("parts") or payload.get("stl_path")))
    if not has_model:
        if show_errors:
            QMessageBox.information(
                page,
                page._t("tool_library.preview.window_title", "3D Preview"),
                page._t("tool_library.preview.none_assigned_selected", "The selected item has no 3D model assigned."),
            )
        if dialog_visible and not show_errors:
            return False
        close_tool_selector_detached_preview(page)
        return False

    if not show_preview_host(
        page,
        payload,
        state_prefix=_STATE_PREFIX,
        geometry_key="tool_detached_preview_dialog",
        measurement_button_attr="_measurement_toggle_btn",
        measurements_enabled_attr="_detached_measurements_enabled",
        close_shortcut_attr="_close_preview_shortcut",
        on_finished_callback=_on_host_finished,
    ):
        close_tool_selector_detached_preview(page)
        return False

    _apply_tool_measurements(page, payload.get("measurement_overlays", []))
    _set_preview_button_checked(page, True)
    return True


def toggle_tool_selector_preview_window(page) -> None:
    _toggle_preview_window(
        page,
        sync_callback=lambda show_errors: sync_tool_selector_detached_preview(page, show_errors=show_errors),
        close_callback=lambda: close_tool_selector_detached_preview(page),
    )


def close_tool_selector_detached_preview(page) -> None:
    close_preview_host(page, state_prefix=_STATE_PREFIX)


def on_fixture_selector_detached_measurements_toggled(page, checked: bool) -> None:
    page._detached_measurements_enabled = bool(checked)
    _update_measurement_icon(page, page._detached_measurements_enabled)
    if getattr(page, "_detached_preview_widget", None) is not None:
        page._detached_preview_widget.set_measurements_visible(page._detached_measurements_enabled)


def on_fixture_selector_detached_preview_closed(page, _result=None) -> None:
    _on_host_finished(page)


def _fixture_transform_payload(fixture: dict) -> dict:
    rot_x, rot_y, rot_z = fixture_preview_rotation(fixture)
    selected_parts = fixture.get("preview_selected_parts", []) or []
    normalized_selected_parts = []
    if isinstance(selected_parts, list):
        for idx in selected_parts:
            try:
                normalized_selected_parts.append(int(idx))
            except Exception:
                continue
    return {
        "alignment_plane": fixture_preview_plane(fixture),
        "rot_x": rot_x,
        "rot_y": rot_y,
        "rot_z": rot_z,
        "transform_mode": str(fixture.get("preview_transform_mode", "translate") or "translate").strip().lower(),
        "fine_transform": bool(fixture.get("preview_fine_transform", False)),
        "selected_part": int(fixture.get("preview_selected_part", -1) or -1),
        "selected_parts": normalized_selected_parts,
    }


def sync_fixture_selector_detached_preview(page, show_errors: bool = False) -> bool:
    preview_button = getattr(page, "preview_window_btn", None)
    if preview_button is None or not preview_button.isChecked():
        return False
    dialog_visible = bool(getattr(page, "_detached_preview_dialog", None) and page._detached_preview_dialog.isVisible())
    if not getattr(page, "current_fixture_id", None):
        if dialog_visible and not show_errors:
            return False
        close_fixture_selector_detached_preview(page)
        return False
    fixture = page.fixture_service.get_fixture(page.current_fixture_id)
    if not fixture or not fixture_preview_has_model_payload(fixture):
        if show_errors:
            QMessageBox.information(
                page,
                page._t("tool_library.preview.window_title", "3D Preview"),
                page._t("tool_library.preview.none_assigned_selected", "The selected item has no 3D model assigned."),
            )
        if dialog_visible and not show_errors:
            return False
        close_fixture_selector_detached_preview(page)
        return False
    parts = fixture_preview_parts_payload(fixture)
    payload = {
        "model_key": page._preview_model_key(fixture),
        "label": fixture_preview_label(fixture, page._t),
        "title": page._t(
            "tool_library.preview.window_title_tool",
            "3D Preview - {tool_id}",
            tool_id=str(fixture.get("fixture_id") or "").strip(),
        ).rstrip(" -"),
        "measurement_overlays": fixture_preview_measurement_overlays(fixture),
        "transform": _fixture_transform_payload(fixture),
    }
    if parts:
        payload["parts"] = parts
    else:
        payload["stl_path"] = fixture_preview_stl_path(fixture)
    if not show_preview_host(
        page,
        payload,
        state_prefix=_STATE_PREFIX,
        geometry_key="fixture_detached_preview_dialog",
        measurement_button_attr="_measurement_toggle_btn",
        measurements_enabled_attr="_detached_measurements_enabled",
        close_shortcut_attr="_close_preview_shortcut",
        on_finished_callback=_on_host_finished,
    ):
        close_fixture_selector_detached_preview(page)
        return False
    _apply_domain_measurements(page, payload.get("measurement_overlays", []))
    _set_preview_button_checked(page, True)
    return True


def toggle_fixture_selector_preview_window(page) -> None:
    _toggle_preview_window(
        page,
        sync_callback=lambda show_errors: sync_fixture_selector_detached_preview(page, show_errors=show_errors),
        close_callback=lambda: close_fixture_selector_detached_preview(page),
    )


def close_fixture_selector_detached_preview(page) -> None:
    close_preview_host(page, state_prefix=_STATE_PREFIX)


def on_jaw_selector_detached_measurements_toggled(page, checked: bool) -> None:
    page._detached_measurements_enabled = bool(checked)
    _update_measurement_icon(page, page._detached_measurements_enabled)
    if getattr(page, "_detached_preview_widget", None) is not None:
        page._detached_preview_widget.set_measurements_visible(page._detached_measurements_enabled)


def on_jaw_selector_detached_preview_closed(page, _result=None) -> None:
    _on_host_finished(page)


def _jaw_transform_payload(jaw: dict) -> dict:
    rot_x, rot_y, rot_z = jaw_preview_rotation(jaw)
    selected_parts = jaw.get("preview_selected_parts", []) or []
    normalized_selected_parts = []
    if isinstance(selected_parts, list):
        for idx in selected_parts:
            try:
                normalized_selected_parts.append(int(idx))
            except Exception:
                continue
    return {
        "alignment_plane": jaw_preview_plane(jaw),
        "rot_x": rot_x,
        "rot_y": rot_y,
        "rot_z": rot_z,
        "transform_mode": str(jaw.get("preview_transform_mode", "translate") or "translate").strip().lower(),
        "fine_transform": bool(jaw.get("preview_fine_transform", False)),
        "selected_part": int(jaw.get("preview_selected_part", -1) or -1),
        "selected_parts": normalized_selected_parts,
    }


def sync_jaw_selector_detached_preview(page, show_errors: bool = False) -> bool:
    preview_button = getattr(page, "preview_window_btn", None)
    if preview_button is None or not preview_button.isChecked():
        return False
    dialog_visible = bool(getattr(page, "_detached_preview_dialog", None) and page._detached_preview_dialog.isVisible())
    if not getattr(page, "current_jaw_id", None):
        if dialog_visible and not show_errors:
            return False
        close_jaw_selector_detached_preview(page)
        return False
    jaw = page.jaw_service.get_jaw(page.current_jaw_id)
    if not jaw or not jaw_preview_has_model_payload(jaw):
        if show_errors:
            QMessageBox.information(
                page,
                page._t("tool_library.preview.window_title", "3D Preview"),
                page._t("tool_library.preview.none_assigned_selected", "The selected item has no 3D model assigned."),
            )
        if dialog_visible and not show_errors:
            return False
        close_jaw_selector_detached_preview(page)
        return False
    parts = jaw_preview_parts_payload(jaw)
    payload = {
        "model_key": page._preview_model_key(jaw),
        "label": jaw_preview_label(jaw, page._t),
        "title": page._t(
            "tool_library.preview.window_title_tool",
            "3D Preview - {tool_id}",
            tool_id=str(jaw.get("jaw_id") or "").strip(),
        ).rstrip(" -"),
        "measurement_overlays": jaw_preview_measurement_overlays(jaw),
        "transform": _jaw_transform_payload(jaw),
    }
    if parts:
        payload["parts"] = parts
    else:
        payload["stl_path"] = jaw_preview_stl_path(jaw)
    if not show_preview_host(
        page,
        payload,
        state_prefix=_STATE_PREFIX,
        geometry_key="jaw_detached_preview_dialog",
        measurement_button_attr="_measurement_toggle_btn",
        measurements_enabled_attr="_detached_measurements_enabled",
        close_shortcut_attr="_close_preview_shortcut",
        on_finished_callback=_on_host_finished,
    ):
        close_jaw_selector_detached_preview(page)
        return False
    _apply_domain_measurements(page, payload.get("measurement_overlays", []))
    _set_preview_button_checked(page, True)
    return True


def toggle_jaw_selector_preview_window(page) -> None:
    _toggle_preview_window(
        page,
        sync_callback=lambda show_errors: sync_jaw_selector_detached_preview(page, show_errors=show_errors),
        close_callback=lambda: close_jaw_selector_detached_preview(page),
    )


def close_jaw_selector_detached_preview(page) -> None:
    close_preview_host(page, state_prefix=_STATE_PREFIX)


__all__ = [
    "close_fixture_selector_detached_preview",
    "close_jaw_selector_detached_preview",
    "close_tool_selector_detached_preview",
    "load_fixture_selector_preview_content",
    "load_jaw_selector_preview_content",
    "load_tool_selector_preview_content",
    "on_fixture_selector_detached_measurements_toggled",
    "on_fixture_selector_detached_preview_closed",
    "on_jaw_selector_detached_measurements_toggled",
    "on_jaw_selector_detached_preview_closed",
    "on_tool_selector_detached_measurements_toggled",
    "on_tool_selector_detached_preview_closed",
    "sync_fixture_selector_detached_preview",
    "sync_jaw_selector_detached_preview",
    "sync_tool_selector_detached_preview",
    "toggle_fixture_selector_preview_window",
    "toggle_jaw_selector_preview_window",
    "toggle_tool_selector_preview_window",
]
