from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QRect, QTimer
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


_EXTERNAL_PREFIX = "_external_selector_preview"
_EXTERNAL_GEOMETRY_KEY = "selector_external_preview_dialog"


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


def _state_attr(prefix: str, suffix: str) -> str:
    return f"{prefix}_{suffix}"


def _get_state(window, prefix: str, suffix: str, default=None):
    return getattr(window, _state_attr(prefix, suffix), default)


def _set_state(window, prefix: str, suffix: str, value) -> None:
    setattr(window, _state_attr(prefix, suffix), value)


def _set_toggle_icon(window, enabled: bool, *, measurement_button_attr: str) -> None:
    button = getattr(window, measurement_button_attr, None)
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


def _apply_embedded_host_bounds(window, dialog: QDialog) -> bool:
    host_window = None
    try:
        if hasattr(window, "window"):
            host_window = window.window()
    except Exception:
        host_window = None
    if host_window is None:
        host_window = window
    if host_window is None or not hasattr(host_window, "frameGeometry"):
        return False

    try:
        host_frame = host_window.frameGeometry()
        host_geom = host_window.geometry()
    except Exception:
        return False
    if host_frame.width() <= 0 or host_frame.height() <= 0:
        return False

    width = min(max(520, int(host_frame.width() * 0.37)), 700)
    height = host_frame.bottom() - host_geom.top()
    x = host_frame.right() - width + 1
    y = host_geom.top()

    probe = QGuiApplication.primaryScreen()
    screen = QGuiApplication.screenAt(host_frame.center()) or probe
    if screen is not None:
        avail = screen.availableGeometry()
        x = max(avail.left(), min(x, avail.right() - width + 1))
        y = max(avail.top(), min(y, avail.bottom() - height + 1))

    dialog.setGeometry(x, y, width, height)
    return True


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


def _apply_preferred_bounds(window, dialog: QDialog, *, payload: dict | None = None, geometry_key: str) -> None:
    mode = get_detached_preview_open_mode(SHARED_UI_PREFERENCES_PATH)
    payload = payload if isinstance(payload, dict) else {}
    host_frame_rect = _rect_from_payload(payload.get("host_frame_geometry"))
    host_content_rect = _rect_from_payload(payload.get("host_content_geometry"))
    if mode == "follow_last":
        if restore_window_geometry(dialog, SHARED_UI_PREFERENCES_PATH, geometry_key):
            return
        if host_frame_rect is not None and host_content_rect is not None:
            _apply_bounds_from_host_rects(dialog, host_frame_rect, host_content_rect, side="embedded")
            return
        if _apply_embedded_host_bounds(window, dialog):
            return
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

    if _apply_embedded_host_bounds(window, dialog):
        return

    _apply_default_bounds(dialog)


def _apply_transform_payload(viewer, payload: dict | None) -> None:
    if viewer is None or not isinstance(payload, dict):
        return

    # Restore saved group orientation (base rotation from orientObjectVertically)
    # before applying alignment plane so the coordinate frame matches the editor.
    base_rx = payload.get("base_rot_x")
    base_ry = payload.get("base_rot_y")
    base_rz = payload.get("base_rot_z")
    if base_rx is not None or base_ry is not None or base_rz is not None:
        if hasattr(viewer, 'set_base_rotation'):
            viewer.set_base_rotation(
                float(base_rx or 0),
                float(base_ry or 0),
                float(base_rz or 0),
            )

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


def _on_measurements_toggled(window, checked: bool, *, state_prefix: str, measurement_button_attr: str, measurements_enabled_attr: str) -> None:
    setattr(window, measurements_enabled_attr, bool(checked))
    _set_toggle_icon(window, bool(checked), measurement_button_attr=measurement_button_attr)
    viewer = _get_state(window, state_prefix, "widget")
    if viewer is not None:
        has_measurements = bool(_get_state(window, state_prefix, "overlays", []))
        viewer.set_measurements_visible(bool(checked) and has_measurements)


def _on_preview_dialog_finished(
    window,
    _result: int,
    *,
    state_prefix: str,
    measurement_button_attr: str,
    close_shortcut_attr: str,
    geometry_key: str,
    on_finished_callback=None,
) -> None:
    dialog = _get_state(window, state_prefix, "dialog")
    viewer = _get_state(window, state_prefix, "widget")
    if dialog is not None:
        save_window_geometry(dialog, SHARED_UI_PREFERENCES_PATH, geometry_key)
    if viewer is not None:
        try:
            viewer.set_measurement_focus_index(-1)
        except Exception:
            pass
        release_preview_runtime_widget(viewer)
    _set_state(window, state_prefix, "dialog", None)
    _set_state(window, state_prefix, "widget", None)
    setattr(window, measurement_button_attr, None)
    setattr(window, close_shortcut_attr, None)
    _set_state(window, state_prefix, "overlays", [])
    _set_state(window, state_prefix, "last_model_key", None)
    _set_state(window, state_prefix, "pending_show", False)
    if callable(on_finished_callback):
        on_finished_callback(window)


def _ensure_preview_dialog(
    window,
    *,
    state_prefix: str,
    measurement_button_attr: str,
    measurements_enabled_attr: str,
    close_shortcut_attr: str,
    geometry_key: str,
    on_finished_callback=None,
) -> tuple[QDialog, object | None]:
    dialog = _get_state(window, state_prefix, "dialog")
    viewer = _get_state(window, state_prefix, "widget")
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
    measurement_btn.setChecked(bool(getattr(window, measurements_enabled_attr, True)))
    measurement_btn.setIconSize(QSize(28, 28))
    measurement_btn.setAutoRaise(True)
    measurement_btn.setProperty("topBarIconButton", True)
    measurement_btn.setFixedSize(36, 36)
    measurement_btn.clicked.connect(
        lambda checked: _on_measurements_toggled(
            window,
            checked,
            state_prefix=state_prefix,
            measurement_button_attr=measurement_button_attr,
            measurements_enabled_attr=measurements_enabled_attr,
        )
    )
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

    dialog.finished.connect(
        lambda result: _on_preview_dialog_finished(
            window,
            result,
            state_prefix=state_prefix,
            measurement_button_attr=measurement_button_attr,
            close_shortcut_attr=close_shortcut_attr,
            geometry_key=geometry_key,
            on_finished_callback=on_finished_callback,
        )
    )
    try:
        window.destroyed.connect(dialog.close)
    except Exception:
        pass

    _set_state(window, state_prefix, "dialog", dialog)
    _set_state(window, state_prefix, "widget", viewer)
    setattr(window, measurement_button_attr, measurement_btn)
    _set_state(window, state_prefix, "overlays", [])
    _set_state(window, state_prefix, "last_model_key", None)
    _set_state(window, state_prefix, "pending_show", False)
    _set_toggle_icon(window, bool(getattr(window, measurements_enabled_attr, True)), measurement_button_attr=measurement_button_attr)

    _apply_preferred_bounds(window, dialog, geometry_key=geometry_key)
    return dialog, viewer


def show_preview_host(
    window,
    payload: dict | None,
    *,
    state_prefix: str = _EXTERNAL_PREFIX,
    geometry_key: str = _EXTERNAL_GEOMETRY_KEY,
    measurement_button_attr: str | None = None,
    measurements_enabled_attr: str | None = None,
    close_shortcut_attr: str | None = None,
    on_finished_callback=None,
) -> bool:
    if window is None or not isinstance(payload, dict):
        return False

    measurement_button_attr = measurement_button_attr or _state_attr(state_prefix, "measurement_btn")
    measurements_enabled_attr = measurements_enabled_attr or _state_attr(state_prefix, "measurements_enabled")
    close_shortcut_attr = close_shortcut_attr or _state_attr(state_prefix, "close_shortcut")

    dialog, viewer = _ensure_preview_dialog(
        window,
        state_prefix=state_prefix,
        measurement_button_attr=measurement_button_attr,
        measurements_enabled_attr=measurements_enabled_attr,
        close_shortcut_attr=close_shortcut_attr,
        geometry_key=geometry_key,
        on_finished_callback=on_finished_callback,
    )
    if viewer is None:
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return False

    parts = payload.get("parts", [])
    stl_path = str(payload.get("stl_path") or "").strip()
    label = str(payload.get("label") or payload.get("item_id") or "3D Preview").strip() or "3D Preview"
    model_key = payload.get("model_key")
    model_changed = model_key != _get_state(window, state_prefix, "last_model_key", None)
    suspend_rendering_fn = getattr(viewer, "set_rendering_suspended", None)
    set_content_visible_fn = getattr(viewer, "set_view_content_visible", None)
    dialog_was_visible = dialog.isVisible()

    if callable(set_content_visible_fn):
        try:
            set_content_visible_fn(not (model_changed and not dialog_was_visible))
        except Exception:
            pass

    if not dialog_was_visible:
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    loaded = True
    if model_changed:
        if callable(suspend_rendering_fn):
            try:
                suspend_rendering_fn(True)
            except Exception:
                pass
        if isinstance(parts, list) and parts:
            viewer.load_parts([dict(item) for item in parts if isinstance(item, dict)])
        elif stl_path:
            viewer.load_stl(stl_path, label=label)
        else:
            loaded = False
        if loaded:
            _set_state(window, state_prefix, "last_model_key", model_key)
        else:
            _set_state(window, state_prefix, "last_model_key", None)

    if not loaded:
        close_preview_host(window, state_prefix=state_prefix)
        return False

    overlays = payload.get("measurement_overlays", [])
    if not isinstance(overlays, list):
        overlays = []
    normalized_overlays = [dict(item) for item in overlays if isinstance(item, dict)]
    _set_state(window, state_prefix, "overlays", normalized_overlays)
    viewer.set_measurement_overlays(normalized_overlays)

    measurement_btn = getattr(window, measurement_button_attr, None)
    has_measurements = bool(normalized_overlays)
    measurements_enabled = bool(getattr(window, measurements_enabled_attr, True))
    if measurement_btn is not None:
        measurement_btn.setEnabled(has_measurements)
        measurement_btn.blockSignals(True)
        measurement_btn.setChecked(measurements_enabled and has_measurements)
        measurement_btn.blockSignals(False)
        _set_toggle_icon(window, measurement_btn.isChecked(), measurement_button_attr=measurement_button_attr)

    viewer.set_measurements_visible(has_measurements and measurements_enabled)
    _apply_transform_payload(viewer, payload.get("transform"))

    title = str(payload.get("title") or _translate(window, "tool_library.preview.window_title", "3D Preview")).strip()
    dialog.setWindowTitle(title)
    _apply_preferred_bounds(window, dialog, payload=payload, geometry_key=geometry_key)

    def _finish_initial_visual_update() -> None:
        if hasattr(viewer, "model_loaded"):
            try:
                viewer.model_loaded.disconnect(_finish_initial_visual_update)
            except Exception:
                pass
        if callable(set_content_visible_fn):
            try:
                set_content_visible_fn(True)
            except Exception:
                pass
        if callable(suspend_rendering_fn):
            try:
                suspend_rendering_fn(False)
            except Exception:
                pass

    if model_changed:
        if hasattr(viewer, "model_loaded"):
            viewer.model_loaded.connect(_finish_initial_visual_update)
        QTimer.singleShot(1200, _finish_initial_visual_update)
    else:
        _finish_initial_visual_update()

    dialog.raise_()
    dialog.activateWindow()
    return True


def close_preview_host(window, *, state_prefix: str = _EXTERNAL_PREFIX) -> None:
    dialog = _get_state(window, state_prefix, "dialog", None)
    if dialog is not None:
        dialog.close()


def show_external_selector_preview(window, payload: dict | None) -> bool:
    return show_preview_host(window, payload)


def close_external_selector_preview(window) -> None:
    close_preview_host(window)


__all__ = [
    "close_external_selector_preview",
    "close_preview_host",
    "show_external_selector_preview",
    "show_preview_host",
]
