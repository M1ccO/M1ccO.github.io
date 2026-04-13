"""Detached 3D preview dialog management for HomePage."""

from __future__ import annotations

import json

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
    page.preview_window_btn.blockSignals(True)
    page.preview_window_btn.setChecked(checked)
    page.preview_window_btn.blockSignals(False)


def ensure_detached_preview_dialog(page):
    if page._detached_preview_dialog is not None:
        return

    dialog = QDialog(page)
    dialog.setProperty('detachedPreviewDialog', True)
    dialog.setWindowTitle(page._t('tool_library.preview.window_title', '3D Preview'))
    dialog.resize(620, 820)
    dialog.finished.connect(lambda _result: on_detached_preview_closed(page))
    page._close_preview_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), dialog)
    page._close_preview_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
    page._close_preview_shortcut.activated.connect(dialog.close)

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
    if page._detached_preview_dialog is None:
        return
    host_window = page.window()
    if host_window is None:
        return

    host_frame = host_window.frameGeometry()
    if host_frame.width() <= 0 or host_frame.height() <= 0:
        return

    width = max(520, int(host_frame.width() * 0.37))
    width = min(width, 700)
    max_height = max(420, host_frame.height() - 30)
    height = max(600, int(host_frame.height() * 0.86))
    height = min(height, max_height)

    x = host_frame.right() - width + 1
    y = host_frame.bottom() - height + 1
    min_y = host_frame.top() + 30
    if y < min_y:
        y = min_y

    page._detached_preview_dialog.setGeometry(x, y, width, height)


def update_detached_measurement_toggle_icon(page, enabled: bool):
    if page._measurement_toggle_btn is None:
        return
    is_enabled = bool(enabled)
    icon_name = 'comment_disable.svg' if is_enabled else 'comment.svg'
    page._measurement_toggle_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / icon_name)))
    tooltip = page._t(
        'tool_library.preview.measurements_hide' if is_enabled else 'tool_library.preview.measurements_show',
        'Piilota mittaukset' if is_enabled else 'Näytä mittaukset',
    )
    page._measurement_toggle_btn.setToolTip(tooltip)


def on_detached_preview_closed(page):
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
    if page._detached_preview_dialog is not None:
        page._detached_preview_dialog.close()
    else:
        set_preview_button_checked(page, False)


def sync_detached_preview(page, show_errors: bool = False) -> bool:
    if not page.preview_window_btn.isChecked():
        return False

    if not page.current_tool_id:
        close_detached_preview(page)
        return False

    tool = page._get_selected_tool()
    if not tool:
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
    if page.preview_window_btn.isChecked():
        if not sync_detached_preview(page, show_errors=True):
            set_preview_button_checked(page, False)
        return

    close_detached_preview(page)


def warmup_preview_engine(page) -> None:
    """Pre-create a hidden preview widget to reduce first detail-open latency."""
    from PySide6.QtCore import QTimer

    if StlPreviewWidget is None:
        return

    page._inline_preview_warmup = StlPreviewWidget(parent=page)
    page._inline_preview_warmup.set_control_hint_text(
        page._t(
            'tool_editor.hint.rotate_pan_zoom',
            'Rotate: left mouse • Pan: right mouse • Zoom: mouse wheel',
        )
    )
    page._inline_preview_warmup.hide()

    def _drop_warmup():
        if page._inline_preview_warmup is not None:
            page._inline_preview_warmup.deleteLater()
            page._inline_preview_warmup = None

    QTimer.singleShot(10000, _drop_warmup)
