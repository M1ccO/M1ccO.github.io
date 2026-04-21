"""Detached 3D preview dialog management for HomePage."""

from __future__ import annotations

import json

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import TOOL_ICONS_DIR
from config import SHARED_UI_PREFERENCES_PATH
from shared.ui.helpers.window_geometry_memory import (
    get_detached_preview_open_mode,
    place_dialog_near_host,
    restore_window_geometry,
    save_window_geometry,
)
from shared.ui.helpers.detached_preview_common import (
    apply_detached_preview_default_bounds as _apply_detached_preview_default_bounds,
    bind_escape_close_shortcut,
    close_detached_preview as _close_detached_preview,
    create_detached_preview_dialog,
    set_preview_button_checked as _set_preview_button_checked,
    toggle_preview_window as _toggle_preview_window,
    update_measurement_toggle_icon,
)
from shared.ui.stl_preview import StlPreviewWidget


def load_preview_content(viewer, stl_path: str | None, label: str | None = None) -> bool:
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


def set_preview_button_checked(page, checked: bool):
    _set_preview_button_checked(page, checked)


def ensure_detached_preview_dialog(page):
    if page._detached_preview_dialog is not None:
        return

    dialog = create_detached_preview_dialog(
        page,
        title=page._t('tool_library.preview.window_title', '3D Preview'),
        on_finished=lambda _result: on_detached_preview_closed(page),
    )
    dialog.resize(620, 820)
    bind_escape_close_shortcut(page, dialog)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(8)

    controls_host = QWidget(dialog)
    controls_host.setProperty('detachedPreviewToolbar', True)
    controls_host.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    controls_layout = QHBoxLayout(controls_host)
    controls_layout.setContentsMargins(0, 0, 0, 0)
    controls_layout.setSpacing(8)
    controls_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    page._measurement_toggle_btn = QToolButton(controls_host)
    page._measurement_toggle_btn.setCheckable(True)
    page._measurement_toggle_btn.setChecked(page._detached_measurements_enabled)
    page._measurement_toggle_btn.setIconSize(QSize(28, 28))
    page._measurement_toggle_btn.setAutoRaise(True)
    page._measurement_toggle_btn.setProperty('topBarIconButton', True)
    page._measurement_toggle_btn.setFixedSize(36, 36)
    update_detached_measurement_toggle_icon(page, page._measurement_toggle_btn.isChecked())
    page._measurement_toggle_btn.clicked.connect(lambda checked: on_detached_measurements_toggled(page, checked))
    controls_layout.addWidget(page._measurement_toggle_btn)

    measurements_label = QLabel(page._t('tool_library.preview.measurements_label', 'Mittaukset'))
    measurements_label.setProperty('detailHint', True)
    measurements_label.setProperty('detachedPreviewToolbarLabel', True)
    measurements_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    controls_layout.addWidget(measurements_label)

    page._measurement_filter_combo = None
    controls_layout.addStretch(1)
    layout.addWidget(controls_host)

    if StlPreviewWidget is not None:
        page._detached_preview_widget = StlPreviewWidget()
        page._detached_preview_widget.set_control_hint_text(
            page._t(
                'tool_editor.hint.rotate_pan_zoom',
                'Rotate: left mouse \u2022 Pan: right mouse \u2022 Zoom: mouse wheel',
            )
        )
        page._detached_preview_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(page._detached_preview_widget, 1)
    else:
        fallback = QLabel(page._t('tool_library.preview.unavailable', 'Preview component not available.'))
        fallback.setWordWrap(True)
        fallback.setAlignment(Qt.AlignCenter)
        page._detached_preview_widget = None
        fallback.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(fallback, 1)

    page._detached_preview_dialog = dialog
    refresh_detached_measurement_controls(page, [])


def apply_detached_preview_default_bounds(page):
    dialog = getattr(page, '_detached_preview_dialog', None)
    if dialog is None:
        return

    mode = get_detached_preview_open_mode(SHARED_UI_PREFERENCES_PATH)
    if mode == 'follow_last':
        if restore_window_geometry(dialog, SHARED_UI_PREFERENCES_PATH, 'tool_detached_preview_dialog'):
            return
        _apply_detached_preview_default_bounds(page)
        return

    if mode == 'left':
        place_dialog_near_host(dialog, page.window(), side='left')
        return

    if mode == 'right':
        place_dialog_near_host(dialog, page.window(), side='right')
        return

    # mode == 'embedded': position dialog as a floating window relative to main window
    if mode == 'embedded':
        _apply_detached_preview_default_bounds(page)
        return


def update_detached_measurement_toggle_icon(page, enabled: bool):
    update_measurement_toggle_icon(
        page,
        bool(enabled),
        icons_dir=TOOL_ICONS_DIR,
        translate=page._t,
        hide_key='tool_library.preview.measurements_hide',
        show_key='tool_library.preview.measurements_show',
        hide_default='Piilota mittaukset',
        show_default='Näytä mittaukset',
    )


def on_detached_preview_closed(page):
    dialog = getattr(page, '_detached_preview_dialog', None)
    if dialog is not None:
        save_window_geometry(dialog, SHARED_UI_PREFERENCES_PATH, 'tool_detached_preview_dialog')
    if page._detached_preview_widget is not None:
        page._detached_preview_widget.set_measurement_focus_index(-1)
    page._detached_preview_last_model_key = None
    set_preview_button_checked(page, False)


def refresh_detached_measurement_controls(page, overlays):
    if page._measurement_toggle_btn is None:
        return

    names = []
    seen = set()
    for overlay in overlays or []:
        if not isinstance(overlay, dict):
            continue
        name = str(overlay.get('name') or '').strip()
        if not name or name in seen:
            continue
        names.append(name)
        seen.add(name)

    has_measurements = bool(names)
    page._measurement_toggle_btn.setEnabled(has_measurements)

    page._measurement_toggle_btn.blockSignals(True)
    page._measurement_toggle_btn.setChecked(page._detached_measurements_enabled and has_measurements)
    page._measurement_toggle_btn.blockSignals(False)
    update_detached_measurement_toggle_icon(page, page._measurement_toggle_btn.isChecked())
    page._detached_measurement_filter = None


def apply_detached_measurement_state(page, overlays):
    if page._detached_preview_widget is None:
        return
    page._detached_preview_widget.set_measurement_overlays(overlays or [])
    page._detached_preview_widget.set_measurements_visible(
        bool(overlays) and page._detached_measurements_enabled
    )
    page._detached_preview_widget.set_measurement_filter(page._detached_measurement_filter)


def on_detached_measurements_toggled(page, checked: bool):
    page._detached_measurements_enabled = bool(checked)
    update_detached_measurement_toggle_icon(page, page._detached_measurements_enabled)
    if page._detached_preview_widget is not None:
        page._detached_preview_widget.set_measurements_visible(page._detached_measurements_enabled)


def close_detached_preview(page):
    _close_detached_preview(page)


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

    stl_path = tool.get('stl_path')
    if not stl_path:
        if show_errors:
            QMessageBox.information(
                page,
                page._t('tool_library.preview.window_title', '3D Preview'),
                page._t('tool_library.preview.none_assigned_selected', 'The selected tool has no 3D model assigned.'),
            )
        if dialog_visible and not show_errors:
            return False
        close_detached_preview(page)
        return False

    ensure_detached_preview_dialog(page)
    was_visible = bool(page._detached_preview_dialog and page._detached_preview_dialog.isVisible())
    label = tool.get('description', '').strip() or tool.get('id', '3D Preview')
    raw_model_key = stl_path if isinstance(stl_path, str) else json.dumps(stl_path, ensure_ascii=False, sort_keys=True)
    model_key = (
        int(tool.get('uid')) if str(tool.get('uid', '')).strip().isdigit() else str(tool.get('id') or '').strip(),
        str(raw_model_key or ''),
    )
    loaded = True
    if page._detached_preview_last_model_key != model_key:
        loaded = load_preview_content(page._detached_preview_widget, stl_path, label=label)
        if loaded:
            page._detached_preview_last_model_key = model_key
        else:
            page._detached_preview_last_model_key = None
    if not loaded:
        if show_errors:
            QMessageBox.information(
                page,
                page._t('tool_library.preview.window_title', '3D Preview'),
                page._t('tool_library.preview.no_valid_selected', 'No valid 3D model data found for the selected tool.'),
            )
        close_detached_preview(page)
        return False

    overlays = tool.get('measurement_overlays', []) if isinstance(tool, dict) else []
    refresh_detached_measurement_controls(page, overlays)
    apply_detached_measurement_state(page, overlays)

    tool_id = page._tool_id_display_value(tool.get('id', ''))
    page._detached_preview_dialog.setWindowTitle(
        page._t('tool_library.preview.window_title_tool', '3D Preview - {tool_id}', tool_id=tool_id).rstrip(' -')
    )
    if not was_visible:
        apply_detached_preview_default_bounds(page)
        page._detached_preview_dialog.show()
        page._detached_preview_dialog.raise_()
        page._detached_preview_dialog.activateWindow()
    set_preview_button_checked(page, True)
    return True


def toggle_preview_window(page):
    _toggle_preview_window(
        page,
        sync_callback=lambda show_errors: sync_detached_preview(page, show_errors=show_errors),
        close_callback=lambda: close_detached_preview(page),
    )
