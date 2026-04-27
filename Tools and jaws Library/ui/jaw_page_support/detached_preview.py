"""Detached preview window helpers for JawPage."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from config import TOOL_ICONS_DIR
from shared.ui.helpers.detached_preview_common import (
    set_preview_button_checked as _set_preview_button_checked,
    toggle_preview_window as _toggle_preview_window,
    update_measurement_toggle_icon,
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
_GEOMETRY_KEY = "jaw_detached_preview_dialog"


def set_preview_button_checked(page, checked: bool) -> None:
    _set_preview_button_checked(page, checked)


def load_preview_content(page, viewer, jaw: dict, *, label: str | None = None) -> bool:
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


def update_detached_measurement_toggle_icon(page, enabled: bool) -> None:
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


def on_detached_measurements_toggled(page, checked: bool) -> None:
    page._detached_measurements_enabled = bool(checked)
    update_detached_measurement_toggle_icon(page, page._detached_measurements_enabled)
    if page._detached_preview_widget is not None:
        page._detached_preview_widget.set_measurements_visible(page._detached_measurements_enabled)


def apply_detached_measurement_state(page, jaw: dict) -> None:
    if page._detached_preview_widget is None:
        return
    overlays = jaw_preview_measurement_overlays(jaw)
    page._detached_preview_widget.set_measurement_overlays(overlays)
    page._detached_preview_widget.set_measurements_visible(bool(overlays) and page._detached_measurements_enabled)
    if page._measurement_toggle_btn is not None:
        page._measurement_toggle_btn.setEnabled(bool(overlays))


def _on_preview_host_finished(page) -> None:
    page._measurement_toggle_btn = None
    page._detached_preview_last_model_key = None
    set_preview_button_checked(page, False)


def ensure_detached_preview_dialog(page) -> None:
    if getattr(page, "_detached_preview_dialog", None) is not None:
        return
    sync_detached_preview(page, show_errors=False)


def apply_detached_preview_default_bounds(page) -> None:
    _ = page


def on_detached_preview_closed(page, _result=None) -> None:
    _on_preview_host_finished(page)


def _build_transform_payload(jaw: dict) -> dict:
    rot_x, rot_y, rot_z = jaw_preview_rotation(jaw)
    selected_parts = jaw.get("preview_selected_parts", []) or []
    normalized_selected_parts = []
    if isinstance(selected_parts, list):
        for idx in selected_parts:
            try:
                normalized_selected_parts.append(int(idx))
            except Exception:
                continue
    payload = {
        "alignment_plane": jaw_preview_plane(jaw),
        "rot_x": rot_x,
        "rot_y": rot_y,
        "rot_z": rot_z,
        "transform_mode": str(jaw.get("preview_transform_mode", "translate") or "translate").strip().lower(),
        "fine_transform": bool(jaw.get("preview_fine_transform", False)),
        "selected_part": int(jaw.get("preview_selected_part", -1) or -1),
        "selected_parts": normalized_selected_parts,
    }
    base_rx = float(jaw.get("preview_base_rot_x") or 0)
    base_ry = float(jaw.get("preview_base_rot_y") or 0)
    base_rz = float(jaw.get("preview_base_rot_z") or 0)
    if base_rx or base_ry or base_rz:
        payload["base_rot_x"] = base_rx
        payload["base_rot_y"] = base_ry
        payload["base_rot_z"] = base_rz
    return payload


def _build_preview_payload(page, jaw: dict) -> dict:
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
        "transform": _build_transform_payload(jaw),
    }
    if parts:
        payload["parts"] = parts
    else:
        payload["stl_path"] = jaw_preview_stl_path(jaw)
    return payload


def close_detached_preview(page) -> None:
    close_preview_host(page, state_prefix=_STATE_PREFIX)


def sync_detached_preview(page, show_errors: bool = False) -> bool:
    if not page.preview_window_btn.isChecked():
        return False
    dialog_visible = bool(page._detached_preview_dialog and page._detached_preview_dialog.isVisible())
    if not page.current_jaw_id:
        if dialog_visible and not show_errors:
            return False
        close_detached_preview(page)
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
        close_detached_preview(page)
        return False

    if not show_preview_host(
        page,
        _build_preview_payload(page, jaw),
        state_prefix=_STATE_PREFIX,
        geometry_key=_GEOMETRY_KEY,
        measurement_button_attr="_measurement_toggle_btn",
        measurements_enabled_attr="_detached_measurements_enabled",
        close_shortcut_attr="_close_preview_shortcut",
        on_finished_callback=_on_preview_host_finished,
    ):
        close_detached_preview(page)
        return False

    apply_detached_measurement_state(page, jaw)
    set_preview_button_checked(page, True)
    return True


def toggle_preview_window(page) -> None:
    _toggle_preview_window(
        page,
        sync_callback=lambda show_errors: sync_detached_preview(page, show_errors=show_errors),
        close_callback=lambda: close_detached_preview(page),
    )


__all__ = [
    "apply_detached_measurement_state",
    "apply_detached_preview_default_bounds",
    "close_detached_preview",
    "ensure_detached_preview_dialog",
    "load_preview_content",
    "on_detached_measurements_toggled",
    "on_detached_preview_closed",
    "set_preview_button_checked",
    "sync_detached_preview",
    "toggle_preview_window",
    "update_detached_measurement_toggle_icon",
]
