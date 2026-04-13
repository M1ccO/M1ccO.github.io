"""Detached preview window helpers for JawPage."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
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
from shared.ui.stl_preview import StlPreviewWidget
from ui.jaw_page_support.preview_rules import (
    apply_jaw_preview_transform,
    jaw_preview_has_model_payload,
    jaw_preview_label,
    jaw_preview_measurement_overlays,
    jaw_preview_parts_payload,
    jaw_preview_stl_path,
)


def set_preview_button_checked(page, checked: bool) -> None:
    if not hasattr(page, 'preview_window_btn'):
        return
    page.preview_window_btn.blockSignals(True)
    page.preview_window_btn.setChecked(checked)
    page.preview_window_btn.blockSignals(False)


def load_preview_content(page, viewer: StlPreviewWidget, jaw: dict, *, label: str | None = None) -> bool:
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


def ensure_detached_preview_dialog(page) -> None:
    if page._detached_preview_dialog is not None:
        return

    dialog = QDialog(page)
    dialog.setProperty('detachedPreviewDialog', True)
    dialog.setWindowTitle(page._t('tool_library.preview.window_title', '3D Preview'))
    dialog.resize(620, 820)
    dialog.finished.connect(page._on_detached_preview_closed)
    page._close_preview_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), dialog)
    page._close_preview_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
    page._close_preview_shortcut.activated.connect(dialog.close)

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
    if page._detached_preview_dialog is None:
        return
    host_window = page.window()
    if host_window is None:
        return
    host_frame = host_window.frameGeometry()
    if host_frame.width() <= 0 or host_frame.height() <= 0:
        return
    width = min(max(520, int(host_frame.width() * 0.37)), 700)
    max_height = max(420, host_frame.height() - 30)
    height = min(max(600, int(host_frame.height() * 0.86)), max_height)
    x = host_frame.right() - width + 1
    y = max(host_frame.top() + 30, host_frame.bottom() - height + 1)
    page._detached_preview_dialog.setGeometry(x, y, width, height)


def update_detached_measurement_toggle_icon(page, enabled: bool) -> None:
    if page._measurement_toggle_btn is None:
        return
    icon_name = 'comment_disable.svg' if enabled else 'comment.svg'
    page._measurement_toggle_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / icon_name)))
    page._measurement_toggle_btn.setToolTip(
        page._t(
            'tool_library.preview.measurements_hide' if enabled else 'tool_library.preview.measurements_show',
            'Piilota mittaukset' if enabled else 'N\xe4yt\xe4 mittaukset',
        )
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


def on_detached_preview_closed(page, _result) -> None:
    if page._detached_preview_widget is not None:
        page._detached_preview_widget.set_measurement_focus_index(-1)
    page._detached_preview_last_model_key = None
    set_preview_button_checked(page, False)


def close_detached_preview(page) -> None:
    if page._detached_preview_dialog is not None:
        page._detached_preview_dialog.close()
    else:
        set_preview_button_checked(page, False)


def sync_detached_preview(page, show_errors: bool = False) -> bool:
    if not page.preview_window_btn.isChecked():
        return False
    if not page.current_jaw_id:
        close_detached_preview(page)
        return False

    jaw = page.jaw_service.get_jaw(page.current_jaw_id)
    if not jaw or not jaw_preview_has_model_payload(jaw):
        if show_errors:
            QMessageBox.information(
                page,
                page._t('tool_library.preview.window_title', '3D Preview'),
                page._t('tool_library.preview.none_assigned_selected', 'The selected item has no 3D model assigned.'),
            )
        close_detached_preview(page)
        return False

    ensure_detached_preview_dialog(page)
    was_visible = bool(page._detached_preview_dialog and page._detached_preview_dialog.isVisible())
    model_key = page._preview_model_key(jaw)
    loaded = True
    if page._detached_preview_last_model_key != model_key:
        loaded = load_preview_content(page, page._detached_preview_widget, jaw, label=jaw_preview_label(jaw, page._t))
        if loaded:
            apply_jaw_preview_transform(page._detached_preview_widget, jaw)
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

    apply_detached_measurement_state(page, jaw)
    jaw_id = str(jaw.get('jaw_id') or '').strip()
    page._detached_preview_dialog.setWindowTitle(
        page._t('tool_library.preview.window_title_tool', '3D Preview - {tool_id}', tool_id=jaw_id).rstrip(' -')
    )
    if not was_visible:
        apply_detached_preview_default_bounds(page)
        page._detached_preview_dialog.show()
        page._detached_preview_dialog.raise_()
        page._detached_preview_dialog.activateWindow()
    set_preview_button_checked(page, True)
    return True


def toggle_preview_window(page) -> None:
    if page.preview_window_btn.isChecked():
        if not sync_detached_preview(page, show_errors=True):
            set_preview_button_checked(page, False)
        return
    close_detached_preview(page)


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
