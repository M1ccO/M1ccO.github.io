"""Detached preview window helpers for FixturePage."""

from __future__ import annotations

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
    set_preview_button_checked as _set_preview_button_checked,
    toggle_preview_window as _toggle_preview_window,
    update_measurement_toggle_icon,
)
from shared.ui.stl_preview import StlPreviewWidget
from ui.fixture_page_support.preview_rules import (
    apply_fixture_preview_transform,
    fixture_preview_has_model_payload,
    fixture_preview_label,
    fixture_preview_measurement_overlays,
    fixture_preview_parts_payload,
    fixture_preview_stl_path,
)


def set_preview_button_checked(page, checked: bool) -> None:
    _set_preview_button_checked(page, checked)


def load_preview_content(page, viewer: StlPreviewWidget, fixture: dict, *, label: str | None = None) -> bool:
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


def ensure_detached_preview_dialog(page) -> None:
    if page._detached_preview_dialog is not None:
        return

    dialog = QDialog(page)
    dialog.setProperty('detachedPreviewDialog', True)
    dialog.setWindowTitle(page._t('tool_library.preview.window_title', '3D Preview'))
    dialog.resize(620, 820)
    dialog.finished.connect(page._on_detached_preview_closed)
    bind_escape_close_shortcut(page, dialog)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(8)

    controls_host = QWidget(dialog)
    controls_host.setProperty('detachedPreviewToolbar', True)
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
    page._measurement_toggle_btn.clicked.connect(page._on_detached_measurements_toggled)
    controls_layout.addWidget(page._measurement_toggle_btn)

    measurements_label = QLabel(page._t('tool_library.preview.measurements_label', 'Mittaukset'))
    measurements_label.setProperty('detailHint', True)
    measurements_label.setProperty('detachedPreviewToolbarLabel', True)
    measurements_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    controls_layout.addWidget(measurements_label)
    controls_layout.addStretch(1)
    layout.addWidget(controls_host)

    page._detached_preview_widget = StlPreviewWidget()
    page._detached_preview_widget.set_control_hint_text(
        page._t(
            'tool_editor.hint.rotate_pan_zoom',
            'Rotate: left mouse \u2022 Pan: right mouse \u2022 Zoom: mouse wheel',
        )
    )
    page._detached_preview_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    layout.addWidget(page._detached_preview_widget, 1)

    page._detached_preview_dialog = dialog


def apply_detached_preview_default_bounds(page) -> None:
    dialog = getattr(page, '_detached_preview_dialog', None)
    if dialog is None:
        return

    mode = get_detached_preview_open_mode(SHARED_UI_PREFERENCES_PATH)
    if mode == 'follow_last':
        if restore_window_geometry(dialog, SHARED_UI_PREFERENCES_PATH, 'jaw_detached_preview_dialog'):
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


def update_detached_measurement_toggle_icon(page, enabled: bool) -> None:
    update_measurement_toggle_icon(
        page,
        bool(enabled),
        icons_dir=TOOL_ICONS_DIR,
        translate=page._t,
        hide_key='tool_library.preview.measurements_hide',
        show_key='tool_library.preview.measurements_show',
        hide_default='Piilota mittaukset',
        show_default='Nayta mittaukset',
    )


def on_detached_measurements_toggled(page, checked: bool) -> None:
    page._detached_measurements_enabled = bool(checked)
    update_detached_measurement_toggle_icon(page, page._detached_measurements_enabled)
    if page._detached_preview_widget is not None:
        page._detached_preview_widget.set_measurements_visible(page._detached_measurements_enabled)


def apply_detached_measurement_state(page, fixture: dict) -> None:
    if page._detached_preview_widget is None:
        return
    overlays = fixture_preview_measurement_overlays(fixture)
    page._detached_preview_widget.set_measurement_overlays(overlays)
    page._detached_preview_widget.set_measurements_visible(bool(overlays) and page._detached_measurements_enabled)
    if page._measurement_toggle_btn is not None:
        page._measurement_toggle_btn.setEnabled(bool(overlays))


def on_detached_preview_closed(page, _result) -> None:
    dialog = getattr(page, '_detached_preview_dialog', None)
    if dialog is not None:
        save_window_geometry(dialog, SHARED_UI_PREFERENCES_PATH, 'jaw_detached_preview_dialog')
    if page._detached_preview_widget is not None:
        page._detached_preview_widget.set_measurement_focus_index(-1)
    page._detached_preview_last_model_key = None
    set_preview_button_checked(page, False)


def close_detached_preview(page) -> None:
    _close_detached_preview(page)


def sync_detached_preview(page, show_errors: bool = False) -> bool:
    if not page.preview_window_btn.isChecked():
        return False
    dialog_visible = bool(page._detached_preview_dialog and page._detached_preview_dialog.isVisible())
    if not page.current_fixture_id:
        if dialog_visible and not show_errors:
            return False
        close_detached_preview(page)
        return False

    fixture = page.fixture_service.get_fixture(page.current_fixture_id)
    if not fixture or not fixture_preview_has_model_payload(fixture):
        if show_errors:
            QMessageBox.information(
                page,
                page._t('tool_library.preview.window_title', '3D Preview'),
                page._t('tool_library.preview.none_assigned_selected', 'The selected item has no 3D model assigned.'),
            )
        if dialog_visible and not show_errors:
            return False
        close_detached_preview(page)
        return False

    ensure_detached_preview_dialog(page)
    was_visible = bool(page._detached_preview_dialog and page._detached_preview_dialog.isVisible())
    model_key = page._preview_model_key(fixture)
    loaded = True
    if page._detached_preview_last_model_key != model_key:
        loaded = load_preview_content(page, page._detached_preview_widget, fixture, label=fixture_preview_label(fixture, page._t))
        if loaded:
            apply_fixture_preview_transform(page._detached_preview_widget, fixture)
            page._detached_preview_last_model_key = model_key
        else:
            page._detached_preview_last_model_key = None
    if not loaded:
        if show_errors:
            QMessageBox.information(
                page,
                page._t('tool_library.preview.window_title', '3D Preview'),
                page._t('tool_library.preview.no_valid_selected', 'No valid 3D model data found for the selected item.'),
            )
        close_detached_preview(page)
        return False

    apply_detached_measurement_state(page, fixture)
    fixture_id = str(fixture.get('fixture_id') or '').strip()
    page._detached_preview_dialog.setWindowTitle(
        page._t('tool_library.preview.window_title_tool', '3D Preview - {tool_id}', tool_id=fixture_id).rstrip(' -')
    )
    if not was_visible:
        apply_detached_preview_default_bounds(page)
        page._detached_preview_dialog.show()
        page._detached_preview_dialog.raise_()
        page._detached_preview_dialog.activateWindow()
    set_preview_button_checked(page, True)
    return True


def toggle_preview_window(page) -> None:
    _toggle_preview_window(
        page,
        sync_callback=lambda show_errors: sync_detached_preview(page, show_errors=show_errors),
        close_callback=lambda: close_detached_preview(page),
    )


def warmup_preview_engine(page) -> None:
    """Pre-create a hidden preview widget to reduce first detail-open latency."""
    from PySide6.QtCore import QTimer

    if StlPreviewWidget is None:
        return

    if getattr(page, '_inline_preview_warmup', None) is not None:
        return

    page._inline_preview_warmup = StlPreviewWidget(parent=page)
    page._inline_preview_warmup.set_control_hint_text(
        page._t(
            'tool_editor.hint.rotate_pan_zoom',
            'Rotate: left mouse â€¢ Pan: right mouse â€¢ Zoom: mouse wheel',
        )
    )

    # Force one-time OpenGL initialization offscreen so the first visible
    # detail preview does not appear to close/reopen the whole window.
    page._inline_preview_warmup.setAttribute(Qt.WA_DontShowOnScreen, True)
    page._inline_preview_warmup.setGeometry(-10000, -10000, 8, 8)
    page._inline_preview_warmup.show()
    QTimer.singleShot(0, page._inline_preview_warmup.hide)

    def _drop_warmup():
        if page._inline_preview_warmup is not None:
            page._inline_preview_warmup.deleteLater()
            page._inline_preview_warmup = None

    QTimer.singleShot(10000, _drop_warmup)


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
    "warmup_preview_engine",
]

