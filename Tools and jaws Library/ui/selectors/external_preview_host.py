from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QRect
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout

from config import SHARED_UI_PREFERENCES_PATH, TOOL_ICONS_DIR
from shared.ui.helpers.preview_runtime import claim_prewarmed_preview_widget, release_preview_runtime_widget
from shared.ui.helpers.window_geometry_memory import (
    get_detached_preview_open_mode,
    place_dialog_near_host,
    restore_window_geometry,
    save_window_geometry,
)
from shared.ui.stl_preview import StlPreviewWidget


_GEOMETRY_KEY = "selector_external_preview_dialog"


def _rect_from_payload(raw) -> QRect | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        x, y, width, height = (int(value) for value in raw)
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    return QRect(x, y, width, height)


def _apply_bounds_from_host_rects(dialog: QDialog, frame_rect: QRect, content_rect: QRect, *, side: str = "right") -> None:
    width = min(max(520, int(frame_rect.width() * 0.37)), 700)
    height = frame_rect.bottom() - content_rect.top()

    if str(side).strip().lower() == "left":
        x = frame_rect.left() - width - 1
    elif str(side).strip().lower() == "embedded":
        x = frame_rect.right() - width + 1
    else:
        x = frame_rect.right() + 1
    y = content_rect.top()

    probe = QGuiApplication.primaryScreen()
    screen = QGuiApplication.screenAt(frame_rect.center()) or probe
    if screen is not None:
        avail = screen.availableGeometry()
        x = max(avail.left(), min(x, avail.right() - width + 1))
        y = max(avail.top(), min(y, avail.bottom() - height + 1))

    dialog.setGeometry(x, y, width, height)


def _translate(window, key: str, default: str, **kwargs) -> str:
    translator = getattr(window, "_t", None)
    if callable(translator):
        try:
            return translator(key, default, **kwargs)
        except Exception:
            return default.format(**kwargs) if kwargs else default
    return default.format(**kwargs) if kwargs else default


def _set_toggle_icon(window, enabled: bool) -> None:
    button = getattr(window, "_external_selector_preview_measurement_btn", None)
    if button is None:
        return
    icon_name = "comment_disable.svg" if enabled else "comment.svg"
    button.setIcon(QIcon(str(TOOL_ICONS_DIR / icon_name)))
    button.setToolTip(
        _translate(
            window,
            "tool_library.preview.measurements_hide" if enabled else "tool_library.preview.measurements_show",
            "Hide measurements" if enabled else "Show measurements",
        )
    )


def _apply_default_bounds(dialog: QDialog) -> None:
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return
    available = screen.availableGeometry()
    width = min(720, max(560, available.width() // 3))
    height = min(900, max(640, int(available.height() * 0.8)))
    x = available.right() - width - 24
    y = available.top() + max(24, (available.height() - height) // 2)
    dialog.setGeometry(x, y, width, height)


def _apply_preferred_bounds(window, dialog: QDialog, payload: dict | None = None) -> None:
    mode = get_detached_preview_open_mode(SHARED_UI_PREFERENCES_PATH)
    payload = payload if isinstance(payload, dict) else {}
    host_frame_rect = _rect_from_payload(payload.get("host_frame_geometry"))
    host_content_rect = _rect_from_payload(payload.get("host_content_geometry"))
    if mode == "follow_last":
        if restore_window_geometry(dialog, SHARED_UI_PREFERENCES_PATH, _GEOMETRY_KEY):
            return
        if host_frame_rect is not None and host_content_rect is not None:
            _apply_bounds_from_host_rects(dialog, host_frame_rect, host_content_rect, side="embedded")
        else:
            _apply_default_bounds(dialog)
        return

    if mode == "left":
        if host_frame_rect is not None and host_content_rect is not None:
            _apply_bounds_from_host_rects(dialog, host_frame_rect, host_content_rect, side="left")
        else:
            place_dialog_near_host(dialog, window, side="left")
        return

    if mode == "right":
        if host_frame_rect is not None and host_content_rect is not None:
            _apply_bounds_from_host_rects(dialog, host_frame_rect, host_content_rect, side="right")
        else:
            place_dialog_near_host(dialog, window, side="right")
        return

    if host_frame_rect is not None and host_content_rect is not None:
        _apply_bounds_from_host_rects(dialog, host_frame_rect, host_content_rect, side="embedded")
        return

    _apply_default_bounds(dialog)


def _apply_transform_payload(viewer, payload: dict | None) -> None:
    if viewer is None or not isinstance(payload, dict):
        return

    plane = str(payload.get("alignment_plane") or "XZ").strip().upper()
    if plane not in {"XZ", "XY", "YZ"}:
        plane = "XZ"

    viewer.set_alignment_plane(plane)
    viewer.reset_model_rotation()

    for axis in ("x", "y", "z"):
        value = payload.get(f"rot_{axis}", 0)
        try:
            degrees = float(value or 0)
        except Exception:
            degrees = 0.0
        if degrees:
            viewer.rotate_model(axis, degrees)

    mode = str(payload.get("transform_mode") or "translate").strip().lower()
    if mode in {"translate", "rotate"}:
        viewer.set_transform_mode(mode)
    viewer.set_fine_transform_enabled(bool(payload.get("fine_transform", False)))

    selected_parts = payload.get("selected_parts", [])
    normalized_selected_parts: list[int] = []
    if isinstance(selected_parts, list):
        for index in selected_parts:
            try:
                normalized = int(index)
            except Exception:
                continue
            if normalized >= 0:
                normalized_selected_parts.append(normalized)
    if normalized_selected_parts:
        viewer.select_parts(normalized_selected_parts)
        return

    try:
        selected_part = int(payload.get("selected_part", -1) or -1)
    except Exception:
        selected_part = -1
    viewer.select_part(selected_part)


def _on_measurements_toggled(window, checked: bool) -> None:
    window._external_selector_preview_measurements_enabled = bool(checked)
    _set_toggle_icon(window, bool(checked))
    viewer = getattr(window, "_external_selector_preview_widget", None)
    if viewer is not None:
        has_measurements = bool(getattr(window, "_external_selector_preview_overlays", []))
        viewer.set_measurements_visible(bool(checked) and has_measurements)


def _on_preview_dialog_finished(window, _result: int) -> None:
    dialog = getattr(window, "_external_selector_preview_dialog", None)
    viewer = getattr(window, "_external_selector_preview_widget", None)
    if dialog is not None:
        save_window_geometry(dialog, SHARED_UI_PREFERENCES_PATH, _GEOMETRY_KEY)
    if viewer is not None:
        viewer.set_measurement_focus_index(-1)
        release_preview_runtime_widget(viewer)
    window._external_selector_preview_dialog = None
    window._external_selector_preview_widget = None
    window._external_selector_preview_measurement_btn = None
    window._external_selector_preview_close_shortcut = None
    window._external_selector_preview_overlays = []
    window._external_selector_preview_last_model_key = None


def _ensure_external_preview_dialog(window) -> tuple[QDialog, object | None]:
    dialog = getattr(window, "_external_selector_preview_dialog", None)
    viewer = getattr(window, "_external_selector_preview_widget", None)
    if dialog is not None:
        return dialog, viewer

    dialog = QDialog(None, Qt.Tool | Qt.WindowStaysOnTopHint)
    dialog.setAttribute(Qt.WA_StyledBackground, True)
    dialog.setAutoFillBackground(True)
    dialog.setProperty("detachedPreviewDialog", True)
    dialog.setWindowTitle(_translate(window, "tool_library.preview.window_title", "3D Preview"))
    dialog.resize(620, 820)
    try:
        dialog.setPalette(window.palette())
    except Exception:
        pass
    try:
        stylesheet = str(window.styleSheet() or "")
    except Exception:
        stylesheet = ""
    if stylesheet.strip():
        dialog.setStyleSheet(stylesheet)

    root = QVBoxLayout(dialog)
    root.setContentsMargins(8, 8, 8, 8)
    root.setSpacing(8)

    controls_host = QLabel(dialog)
    controls_host.setProperty("detachedPreviewToolbar", True)
    controls_host.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    controls_layout = QHBoxLayout(controls_host)
    controls_layout.setContentsMargins(0, 0, 0, 0)
    controls_layout.setSpacing(8)

    measurement_btn = QToolButton(controls_host)
    measurement_btn.setCheckable(True)
    measurement_btn.setChecked(True)
    measurement_btn.setIconSize(QSize(28, 28))
    measurement_btn.setAutoRaise(True)
    measurement_btn.setProperty("topBarIconButton", True)
    measurement_btn.setFixedSize(36, 36)
    measurement_btn.clicked.connect(lambda checked: _on_measurements_toggled(window, checked))
    controls_layout.addWidget(measurement_btn)

    label = QLabel(_translate(window, "tool_library.preview.measurements_label", "Measurements"), controls_host)
    label.setProperty("detailHint", True)
    label.setProperty("detachedPreviewToolbarLabel", True)
    controls_layout.addWidget(label)
    controls_layout.addStretch(1)
    root.addWidget(controls_host)

    viewer = claim_prewarmed_preview_widget(dialog)
    if viewer is None and StlPreviewWidget is not None:
        viewer = StlPreviewWidget(parent=dialog)

    if viewer is not None:
        viewer.set_control_hint_text(
            _translate(
                window,
                "tool_editor.hint.rotate_pan_zoom",
                "Rotate: left mouse | Pan: right mouse | Zoom: mouse wheel",
            )
        )
        viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(viewer, 1)
        viewer.show()
    else:
        fallback = QLabel(_translate(window, "tool_library.preview.unavailable", "Preview component not available."), dialog)
        fallback.setWordWrap(True)
        fallback.setAlignment(Qt.AlignCenter)
        fallback.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(fallback, 1)

    dialog.finished.connect(lambda result: _on_preview_dialog_finished(window, result))
    try:
        window.destroyed.connect(dialog.close)
    except Exception:
        pass

    window._external_selector_preview_dialog = dialog
    window._external_selector_preview_widget = viewer
    window._external_selector_preview_measurement_btn = measurement_btn
    window._external_selector_preview_overlays = []
    window._external_selector_preview_last_model_key = None
    window._external_selector_preview_measurements_enabled = True
    _set_toggle_icon(window, True)

    _apply_preferred_bounds(window, dialog)
    return dialog, viewer


def show_external_selector_preview(window, payload: dict | None) -> bool:
    if window is None or not isinstance(payload, dict):
        return False

    dialog, viewer = _ensure_external_preview_dialog(window)
    if viewer is None:
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return False

    parts = payload.get("parts", [])
    stl_path = str(payload.get("stl_path") or "").strip()
    label = str(payload.get("label") or payload.get("item_id") or "3D Preview").strip() or "3D Preview"
    model_key = payload.get("model_key")

    loaded = True
    if model_key != getattr(window, "_external_selector_preview_last_model_key", None):
        if isinstance(parts, list) and parts:
            viewer.load_parts([dict(item) for item in parts if isinstance(item, dict)])
        elif stl_path:
            viewer.load_stl(stl_path, label=label)
        else:
            loaded = False
        if loaded:
            window._external_selector_preview_last_model_key = model_key
        else:
            window._external_selector_preview_last_model_key = None

    if not loaded:
        close_external_selector_preview(window)
        return False

    overlays = payload.get("measurement_overlays", [])
    if not isinstance(overlays, list):
        overlays = []
    window._external_selector_preview_overlays = [dict(item) for item in overlays if isinstance(item, dict)]
    viewer.set_measurement_overlays(window._external_selector_preview_overlays)

    measurement_btn = getattr(window, "_external_selector_preview_measurement_btn", None)
    has_measurements = bool(window._external_selector_preview_overlays)
    if measurement_btn is not None:
        measurement_btn.setEnabled(has_measurements)
        measurement_btn.blockSignals(True)
        measurement_btn.setChecked(bool(getattr(window, "_external_selector_preview_measurements_enabled", True)) and has_measurements)
        measurement_btn.blockSignals(False)
        _set_toggle_icon(window, measurement_btn.isChecked())

    viewer.set_measurements_visible(
        has_measurements and bool(getattr(window, "_external_selector_preview_measurements_enabled", True))
    )
    _apply_transform_payload(viewer, payload.get("transform"))

    title = str(payload.get("title") or _translate(window, "tool_library.preview.window_title", "3D Preview")).strip()
    dialog.setWindowTitle(title)
    _apply_preferred_bounds(window, dialog, payload)
    if not dialog.isVisible():
        dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return True


def close_external_selector_preview(window) -> None:
    dialog = getattr(window, "_external_selector_preview_dialog", None)
    if dialog is not None:
        dialog.close()


__all__ = [
    "close_external_selector_preview",
    "show_external_selector_preview",
]