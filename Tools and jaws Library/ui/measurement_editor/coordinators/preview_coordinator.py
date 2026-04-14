"""Preview refresh and sync helpers for the measurement editor.

Stateless module-level functions. No widgets stored here — the dialog wires
its current widgets and callbacks on every call.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QEventLoop, QTimer

from ..bridge.preview_sync import (
    apply_diameter_overlay_update,
    apply_distance_overlay_update,
    compose_preview_overlays,
)


def refresh_preview_measurements(
    preview_widget,
    distance_list,
    diameter_list,
    radius_list,
    angle_list,
    current_distance_item,
    normalize_distance: Callable,
    normalize_diameter: Callable,
    normalize_radius: Callable,
    normalize_angle: Callable,
    distance_precise_mode_enabled: bool,
    distance_adjust_mode: str,
    distance_nudge_point: str,
) -> None:
    distance_overlays: list[dict] = []
    active_uid = ''
    active_point = ''
    if current_distance_item is not None:
        current_data = dict(current_distance_item.data(Qt.UserRole) or {})
        active_uid = str(current_data.get('_uid') or '').strip()
        if (
            active_uid
            and distance_precise_mode_enabled
            and distance_adjust_mode == 'point'
        ):
            active_point = distance_nudge_point
    for i in range(distance_list.count()):
        distance_overlays.append(normalize_distance(distance_list.item(i).data(Qt.UserRole)))
    diameter_overlays: list[dict] = []
    for i in range(diameter_list.count()):
        diameter_overlays.append(normalize_diameter(diameter_list.item(i).data(Qt.UserRole)))
    radius_overlays: list[dict] = []
    for i in range(radius_list.count()):
        radius_overlays.append(normalize_radius(radius_list.item(i).data(Qt.UserRole)))
    angle_overlays: list[dict] = []
    for i in range(angle_list.count()):
        angle_overlays.append(normalize_angle(angle_list.item(i).data(Qt.UserRole)))

    overlays = compose_preview_overlays(
        distance_overlays=distance_overlays,
        diameter_overlays=diameter_overlays,
        radius_overlays=radius_overlays,
        angle_overlays=angle_overlays,
        active_distance_uid=active_uid,
        active_point=active_point,
    )
    preview_widget.set_measurement_overlays(overlays)


def sync_preview_before_save(
    dialog_parent,
    preview_widget,
    on_measurement_updated: Callable,
) -> None:
    if not hasattr(preview_widget, 'get_measurements_snapshot'):
        return
    snapshot = None
    loop = QEventLoop(dialog_parent)

    def _on_snapshot(payload):
        nonlocal snapshot
        snapshot = payload
        if loop.isRunning():
            loop.quit()

    try:
        preview_widget.get_measurements_snapshot(_on_snapshot)
    except Exception:
        return
    QTimer.singleShot(300, loop.quit)
    loop.exec()
    if not isinstance(snapshot, list):
        return
    for idx, overlay in enumerate(snapshot):
        if not isinstance(overlay, dict):
            continue
        on_measurement_updated({'index': idx, 'overlay': overlay})


def on_measurement_updated(
    payload: dict,
    distance_list,
    diameter_list,
    current_distance_item,
    current_diameter_item,
    on_distance_model_updated: Callable,
    on_diameter_model_updated: Callable,
    on_refresh_preview: Callable,
) -> None:
    if not isinstance(payload, dict):
        return
    index = payload.get('index')
    overlay = payload.get('overlay')
    if not isinstance(index, int) or index < 0 or not isinstance(overlay, dict):
        return
    overlay_type = str(overlay.get('type') or '').strip().lower()
    if overlay_type == 'distance':
        if index >= distance_list.count():
            return
        item = distance_list.item(index)
        if item is None:
            return
        current = dict(item.data(Qt.UserRole) or {})
        current = apply_distance_overlay_update(current, overlay)
        item.setData(Qt.UserRole, current)
        if item is current_distance_item:
            on_distance_model_updated(current)
        else:
            on_refresh_preview()
        return

    if overlay_type == 'diameter_ring':
        diameter_index = index - distance_list.count()
        if diameter_index < 0 or diameter_index >= diameter_list.count():
            return
        item = diameter_list.item(diameter_index)
        if item is None:
            return
        current = dict(item.data(Qt.UserRole) or {})
        current = apply_diameter_overlay_update(current, overlay)
        item.setData(Qt.UserRole, current)
        if item is current_diameter_item:
            on_diameter_model_updated(current)
        else:
            on_refresh_preview()


__all__ = [
    "refresh_preview_measurements",
    "sync_preview_before_save",
    "on_measurement_updated",
]
