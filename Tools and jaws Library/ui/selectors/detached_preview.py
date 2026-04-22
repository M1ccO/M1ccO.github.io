from __future__ import annotations

import json

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import SHARED_UI_PREFERENCES_PATH, TOOL_ICONS_DIR
from shared.ui.helpers.detached_preview_common import (
    apply_detached_preview_default_bounds as _apply_detached_preview_default_bounds,
    bind_escape_close_shortcut,
    close_detached_preview as _close_detached_preview,
    create_detached_preview_dialog,
    set_preview_button_checked as _set_preview_button_checked,
    toggle_preview_window as _toggle_preview_window,
    update_measurement_toggle_icon,
)
from shared.ui.helpers.preview_runtime import claim_prewarmed_preview_widget, release_preview_runtime_widget
from shared.ui.helpers.window_geometry_memory import (
    get_detached_preview_open_mode,
    place_dialog_near_host,
    restore_window_geometry,
    save_window_geometry,
)
from shared.ui.stl_preview import StlPreviewWidget
from ..fixture_preview_rules import (
    apply_fixture_preview_transform,
    fixture_preview_has_model_payload,
    fixture_preview_label,
    fixture_preview_measurement_overlays,
    fixture_preview_parts_payload,
    fixture_preview_stl_path,
    fixture_preview_transform_signature,
)
from ..jaw_page_support.preview_rules import (
    apply_jaw_preview_transform,
    jaw_preview_has_model_payload,
    jaw_preview_label,
    jaw_preview_measurement_overlays,
    jaw_preview_parts_payload,
    jaw_preview_stl_path,
)


def _set_preview_button_checked(page, checked: bool) -> None:
    _set_preview_button_checked(page, checked)


def _apply_preview_bounds(page, *, geometry_key: str) -> None:
    dialog = getattr(page, "_detached_preview_dialog", None)
    if dialog is None:
        return

    mode = get_detached_preview_open_mode(SHARED_UI_PREFERENCES_PATH)
    if mode == "follow_last":
        if restore_window_geometry(dialog, SHARED_UI_PREFERENCES_PATH, geometry_key):
            return
        _apply_detached_preview_default_bounds(page)
        return

    if mode == "left":
        place_dialog_near_host(dialog, page.window(), side="left")
        return

    if mode == "right":
        place_dialog_near_host(dialog, page.window(), side="right")
        return

    _apply_detached_preview_default_bounds(page)


def _ensure_selector_detached_preview_dialog(
    page,
    *,
    title: str,
    on_finished,
    on_measurements_toggled,
    update_measurement_icon,
) -> None:
    if getattr(page, "_detached_preview_dialog", None) is not None:
        return

    dialog = create_detached_preview_dialog(page, title=title, on_finished=on_finished)
    dialog.resize(620, 820)
    bind_escape_close_shortcut(page, dialog)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(8)

    controls_host = QWidget(dialog)
    controls_host.setProperty("detachedPreviewToolbar", True)
    controls_host.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    controls_layout = QHBoxLayout(controls_host)
    controls_layout.setContentsMargins(0, 0, 0, 0)
    controls_layout.setSpacing(8)
    controls_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    page._measurement_toggle_btn = QToolButton(controls_host)
    page._measurement_toggle_btn.setCheckable(True)
    page._measurement_toggle_btn.setChecked(bool(getattr(page, "_detached_measurements_enabled", True)))
    page._measurement_toggle_btn.setIconSize(QSize(28, 28))
    page._measurement_toggle_btn.setAutoRaise(True)
    page._measurement_toggle_btn.setProperty("topBarIconButton", True)
    page._measurement_toggle_btn.setFixedSize(36, 36)
    update_measurement_icon(page, page._measurement_toggle_btn.isChecked())
    page._measurement_toggle_btn.clicked.connect(on_measurements_toggled)
    controls_layout.addWidget(page._measurement_toggle_btn)

    measurements_label = QLabel(page._t("tool_library.preview.measurements_label", "Measurements"))
    measurements_label.setProperty("detailHint", True)
    measurements_label.setProperty("detachedPreviewToolbarLabel", True)
    measurements_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    controls_layout.addWidget(measurements_label)
    controls_layout.addStretch(1)
    layout.addWidget(controls_host)

    page._detached_preview_widget = claim_prewarmed_preview_widget(dialog)
    if page._detached_preview_widget is None and StlPreviewWidget is not None:
        page._detached_preview_widget = StlPreviewWidget()

    if page._detached_preview_widget is not None:
        page._detached_preview_widget.set_control_hint_text(
            page._t(
                "tool_editor.hint.rotate_pan_zoom",
                "Rotate: left mouse | Pan: right mouse | Zoom: mouse wheel",
            )
        )
        page._detached_preview_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(page._detached_preview_widget, 1)
        page._detached_preview_widget.show()
    else:
        fallback = QLabel(page._t("tool_library.preview.unavailable", "Preview component not available."))
        fallback.setWordWrap(True)
        fallback.setAlignment(Qt.AlignCenter)
        fallback.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        page._detached_preview_widget = None
        layout.addWidget(fallback, 1)

    page._detached_preview_dialog = dialog


def load_tool_selector_preview_content(viewer, stl_path: str | None, *, label: str | None = None) -> bool:
    if StlPreviewWidget is None or viewer is None or not stl_path:
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


def _update_tool_selector_measurement_toggle_icon(page, enabled: bool) -> None:
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


def on_tool_selector_detached_measurements_toggled(page, checked: bool) -> None:
    page._detached_measurements_enabled = bool(checked)
    _update_tool_selector_measurement_toggle_icon(page, page._detached_measurements_enabled)
    if getattr(page, "_detached_preview_widget", None) is not None:
        page._detached_preview_widget.set_measurements_visible(page._detached_measurements_enabled)


def on_tool_selector_detached_preview_closed(page) -> None:
    dialog = getattr(page, "_detached_preview_dialog", None)
    widget = getattr(page, "_detached_preview_widget", None)
    if dialog is not None:
        save_window_geometry(dialog, SHARED_UI_PREFERENCES_PATH, "tool_detached_preview_dialog")
    if widget is not None:
        widget.set_measurement_focus_index(-1)
        release_preview_runtime_widget(widget)
    page._detached_preview_widget = None
    page._detached_preview_dialog = None
    page._measurement_toggle_btn = None
    page._measurement_filter_combo = None
    page._close_preview_shortcut = None
    page._detached_preview_last_model_key = None
    _set_preview_button_checked(page, False)
    if dialog is not None:
        dialog.deleteLater()


def _refresh_tool_selector_measurement_controls(page, overlays) -> None:
    button = getattr(page, "_measurement_toggle_btn", None)
    if button is None:
        return

    names = []
    seen = set()
    for overlay in overlays or []:
        if not isinstance(overlay, dict):
            continue
        name = str(overlay.get("name") or "").strip()
        if not name or name in seen:
            continue
        names.append(name)
        seen.add(name)

    has_measurements = bool(names)
    button.setEnabled(has_measurements)
    button.blockSignals(True)
    button.setChecked(bool(getattr(page, "_detached_measurements_enabled", True)) and has_measurements)
    button.blockSignals(False)
    _update_tool_selector_measurement_toggle_icon(page, button.isChecked())
    page._detached_measurement_filter = None


def _apply_tool_selector_measurement_state(page, overlays) -> None:
    if getattr(page, "_detached_preview_widget", None) is None:
        return
    page._detached_preview_widget.set_measurement_overlays(overlays or [])
    page._detached_preview_widget.set_measurements_visible(
        bool(overlays) and bool(getattr(page, "_detached_measurements_enabled", True))
    )
    page._detached_preview_widget.set_measurement_filter(getattr(page, "_detached_measurement_filter", None))


def _ensure_tool_selector_detached_preview_dialog(page) -> None:
    _ensure_selector_detached_preview_dialog(
        page,
        title=page._t("tool_library.preview.window_title", "3D Preview"),
        on_finished=lambda _result: on_tool_selector_detached_preview_closed(page),
        on_measurements_toggled=lambda checked: on_tool_selector_detached_measurements_toggled(page, checked),
        update_measurement_icon=_update_tool_selector_measurement_toggle_icon,
    )
    _refresh_tool_selector_measurement_controls(page, [])


def close_tool_selector_detached_preview(page) -> None:
    _close_detached_preview(page)


def sync_tool_selector_detached_preview(page, *, show_errors: bool = False) -> bool:
    preview_button = getattr(page, "preview_window_btn", None)
    if preview_button is None or not preview_button.isChecked():
        return False

    dialog_visible = bool(getattr(page, "_detached_preview_dialog", None) and page._detached_preview_dialog.isVisible())
    if not getattr(page, "current_tool_id", None):
        if dialog_visible and not show_errors:
            return False
        close_tool_selector_detached_preview(page)
        return False

    tool = page._get_selected_tool()
    if not tool:
        if dialog_visible and not show_errors:
            return False
        close_tool_selector_detached_preview(page)
        return False

    stl_path = tool.get("stl_path") if isinstance(tool, dict) else None
    if not stl_path:
        if show_errors:
            QMessageBox.information(
                page,
                page._t("tool_library.preview.window_title", "3D Preview"),
                page._t("tool_library.preview.none_assigned_selected", "The selected tool has no 3D model assigned."),
            )
        if dialog_visible and not show_errors:
            return False
        close_tool_selector_detached_preview(page)
        return False

    _ensure_tool_selector_detached_preview_dialog(page)
    was_visible = bool(getattr(page, "_detached_preview_dialog", None) and page._detached_preview_dialog.isVisible())
    label = str(tool.get("description") or "").strip() or str(tool.get("id") or "3D Preview")
    raw_model_key = stl_path if isinstance(stl_path, str) else json.dumps(stl_path, ensure_ascii=False, sort_keys=True)
    model_key = (
        int(tool.get("uid")) if str(tool.get("uid", "")).strip().isdigit() else str(tool.get("id") or "").strip(),
        str(raw_model_key or ""),
    )
    loaded = True
    if getattr(page, "_detached_preview_last_model_key", None) != model_key:
        loaded = page._load_preview_content(page._detached_preview_widget, stl_path, label=label)
        if loaded:
            page._detached_preview_last_model_key = model_key
        else:
            page._detached_preview_last_model_key = None
    if not loaded:
        if show_errors:
            QMessageBox.information(
                page,
                page._t("tool_library.preview.window_title", "3D Preview"),
                page._t("tool_library.preview.no_valid_selected", "No valid 3D model data found for the selected tool."),
            )
        close_tool_selector_detached_preview(page)
        return False

    overlays = tool.get("measurement_overlays", []) if isinstance(tool, dict) else []
    _refresh_tool_selector_measurement_controls(page, overlays)
    _apply_tool_selector_measurement_state(page, overlays)

    tool_id = page._tool_id_display_value(tool.get("id", ""))
    page._detached_preview_dialog.setWindowTitle(
        page._t("tool_library.preview.window_title_tool", "3D Preview - {tool_id}", tool_id=tool_id).rstrip(" -")
    )
    if not was_visible:
        _apply_preview_bounds(page, geometry_key="tool_detached_preview_dialog")
        page._detached_preview_dialog.show()
        page._detached_preview_dialog.raise_()
        page._detached_preview_dialog.activateWindow()
    _set_preview_button_checked(page, True)
    return True


def toggle_tool_selector_preview_window(page) -> None:
    _toggle_preview_window(
        page,
        sync_callback=lambda show_errors: sync_tool_selector_detached_preview(page, show_errors=show_errors),
        close_callback=lambda: close_tool_selector_detached_preview(page),
    )


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


def _update_jaw_selector_measurement_toggle_icon(page, enabled: bool) -> None:
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


def _update_fixture_selector_measurement_toggle_icon(page, enabled: bool) -> None:
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


def on_fixture_selector_detached_measurements_toggled(page, checked: bool) -> None:
    page._detached_measurements_enabled = bool(checked)
    _update_fixture_selector_measurement_toggle_icon(page, page._detached_measurements_enabled)
    if getattr(page, "_detached_preview_widget", None) is not None:
        page._detached_preview_widget.set_measurements_visible(page._detached_measurements_enabled)


def on_fixture_selector_detached_preview_closed(page, _result) -> None:
    dialog = getattr(page, "_detached_preview_dialog", None)
    widget = getattr(page, "_detached_preview_widget", None)
    if dialog is not None:
        save_window_geometry(dialog, SHARED_UI_PREFERENCES_PATH, "fixture_detached_preview_dialog")
    if widget is not None:
        widget.set_measurement_focus_index(-1)
        release_preview_runtime_widget(widget)
    page._detached_preview_widget = None
    page._detached_preview_dialog = None
    page._measurement_toggle_btn = None
    page._close_preview_shortcut = None
    page._detached_preview_last_model_key = None
    _set_preview_button_checked(page, False)
    if dialog is not None:
        dialog.deleteLater()


def _apply_fixture_selector_measurement_state(page, fixture: dict) -> None:
    if getattr(page, "_detached_preview_widget", None) is None:
        return
    overlays = fixture_preview_measurement_overlays(fixture)
    page._detached_preview_widget.set_measurement_overlays(overlays)
    page._detached_preview_widget.set_measurements_visible(
        bool(overlays) and bool(getattr(page, "_detached_measurements_enabled", True))
    )
    button = getattr(page, "_measurement_toggle_btn", None)
    if button is not None:
        button.setEnabled(bool(overlays))


def _ensure_fixture_selector_detached_preview_dialog(page) -> None:
    _ensure_selector_detached_preview_dialog(
        page,
        title=page._t("tool_library.preview.window_title", "3D Preview"),
        on_finished=lambda result: on_fixture_selector_detached_preview_closed(page, result),
        on_measurements_toggled=lambda checked: on_fixture_selector_detached_measurements_toggled(page, checked),
        update_measurement_icon=_update_fixture_selector_measurement_toggle_icon,
    )


def close_fixture_selector_detached_preview(page) -> None:
    _close_detached_preview(page)


def sync_fixture_selector_detached_preview(page, show_errors: bool = False) -> bool:
    preview_button = getattr(page, "preview_window_btn", None)
    if preview_button is None or not preview_button.isChecked():
        return False

    dialog_visible = bool(getattr(page, "_detached_preview_dialog", None) and page._detached_preview_dialog.isVisible())
    fixture = page._get_selected_fixture()
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

    _ensure_fixture_selector_detached_preview_dialog(page)
    was_visible = bool(getattr(page, "_detached_preview_dialog", None) and page._detached_preview_dialog.isVisible())
    model_key = page._preview_model_key(fixture)
    loaded = True
    if getattr(page, "_detached_preview_last_model_key", None) != model_key:
        loaded = page._load_preview_content(
            page._detached_preview_widget,
            fixture,
            label=fixture_preview_label(fixture, page._t),
        )
        if loaded:
            apply_fixture_preview_transform(page._detached_preview_widget, fixture)
            page._detached_preview_last_model_key = model_key
        else:
            page._detached_preview_last_model_key = None
    if not loaded:
        if show_errors:
            QMessageBox.information(
                page,
                page._t("tool_library.preview.window_title", "3D Preview"),
                page._t("tool_library.preview.no_valid_selected", "No valid 3D model data found for the selected item."),
            )
        close_fixture_selector_detached_preview(page)
        return False

    _apply_fixture_selector_measurement_state(page, fixture)
    fixture_id = str(fixture.get("fixture_id") or "").strip()
    page._detached_preview_dialog.setWindowTitle(
        page._t("tool_library.preview.window_title_tool", "3D Preview - {tool_id}", tool_id=fixture_id).rstrip(" -")
    )
    if not was_visible:
        _apply_preview_bounds(page, geometry_key="fixture_detached_preview_dialog")
        page._detached_preview_dialog.show()
        page._detached_preview_dialog.raise_()
        page._detached_preview_dialog.activateWindow()
    _set_preview_button_checked(page, True)
    return True


def toggle_fixture_selector_preview_window(page) -> None:
    _toggle_preview_window(
        page,
        sync_callback=lambda show_errors: sync_fixture_selector_detached_preview(page, show_errors=show_errors),
        close_callback=lambda: close_fixture_selector_detached_preview(page),
    )


def on_jaw_selector_detached_measurements_toggled(page, checked: bool) -> None:
    page._detached_measurements_enabled = bool(checked)
    _update_jaw_selector_measurement_toggle_icon(page, page._detached_measurements_enabled)
    if getattr(page, "_detached_preview_widget", None) is not None:
        page._detached_preview_widget.set_measurements_visible(page._detached_measurements_enabled)


def on_jaw_selector_detached_preview_closed(page, _result) -> None:
    dialog = getattr(page, "_detached_preview_dialog", None)
    widget = getattr(page, "_detached_preview_widget", None)
    if dialog is not None:
        save_window_geometry(dialog, SHARED_UI_PREFERENCES_PATH, "jaw_detached_preview_dialog")
    if widget is not None:
        widget.set_measurement_focus_index(-1)
        release_preview_runtime_widget(widget)
    page._detached_preview_widget = None
    page._detached_preview_dialog = None
    page._measurement_toggle_btn = None
    page._close_preview_shortcut = None
    page._detached_preview_last_model_key = None
    _set_preview_button_checked(page, False)
    if dialog is not None:
        dialog.deleteLater()


def _apply_jaw_selector_measurement_state(page, jaw: dict) -> None:
    if getattr(page, "_detached_preview_widget", None) is None:
        return
    overlays = jaw_preview_measurement_overlays(jaw)
    page._detached_preview_widget.set_measurement_overlays(overlays)
    page._detached_preview_widget.set_measurements_visible(
        bool(overlays) and bool(getattr(page, "_detached_measurements_enabled", True))
    )
    button = getattr(page, "_measurement_toggle_btn", None)
    if button is not None:
        button.setEnabled(bool(overlays))


def _ensure_jaw_selector_detached_preview_dialog(page) -> None:
    _ensure_selector_detached_preview_dialog(
        page,
        title=page._t("tool_library.preview.window_title", "3D Preview"),
        on_finished=lambda result: on_jaw_selector_detached_preview_closed(page, result),
        on_measurements_toggled=lambda checked: on_jaw_selector_detached_measurements_toggled(page, checked),
        update_measurement_icon=_update_jaw_selector_measurement_toggle_icon,
    )


def close_jaw_selector_detached_preview(page) -> None:
    _close_detached_preview(page)


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

    _ensure_jaw_selector_detached_preview_dialog(page)
    was_visible = bool(getattr(page, "_detached_preview_dialog", None) and page._detached_preview_dialog.isVisible())
    model_key = page._preview_model_key(jaw)
    loaded = True
    if getattr(page, "_detached_preview_last_model_key", None) != model_key:
        loaded = page._load_preview_content(page._detached_preview_widget, jaw, label=jaw_preview_label(jaw, page._t))
        if loaded:
            apply_jaw_preview_transform(page._detached_preview_widget, jaw)
            page._detached_preview_last_model_key = model_key
        else:
            page._detached_preview_last_model_key = None
    if not loaded:
        if show_errors:
            QMessageBox.information(
                page,
                page._t("tool_library.preview.window_title", "3D Preview"),
                page._t("tool_library.preview.no_valid_selected", "No valid 3D model data found for the selected item."),
            )
        close_jaw_selector_detached_preview(page)
        return False

    _apply_jaw_selector_measurement_state(page, jaw)
    jaw_id = str(jaw.get("jaw_id") or "").strip()
    page._detached_preview_dialog.setWindowTitle(
        page._t("tool_library.preview.window_title_tool", "3D Preview - {tool_id}", tool_id=jaw_id).rstrip(" -")
    )
    if not was_visible:
        _apply_preview_bounds(page, geometry_key="jaw_detached_preview_dialog")
        page._detached_preview_dialog.show()
        page._detached_preview_dialog.raise_()
        page._detached_preview_dialog.activateWindow()
    _set_preview_button_checked(page, True)
    return True


def toggle_jaw_selector_preview_window(page) -> None:
    _toggle_preview_window(
        page,
        sync_callback=lambda show_errors: sync_jaw_selector_detached_preview(page, show_errors=show_errors),
        close_callback=lambda: close_jaw_selector_detached_preview(page),
    )


__all__ = [
    "close_fixture_selector_detached_preview",
    "load_jaw_selector_preview_content",
    "load_fixture_selector_preview_content",
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