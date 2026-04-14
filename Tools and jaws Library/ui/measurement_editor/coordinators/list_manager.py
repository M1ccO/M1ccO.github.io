"""Measurement list manager for the measurement editor.

Owns the unified all-list and the four hidden type lists. Handles add,
remove, rebuild, populate, and all-list selection dispatch. Does not
manage edit-form state — delegates to the dialog via callbacks.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from ..controllers.measurement_registry import (
    find_item_by_uid as _find_item_by_uid_fn,
    measurement_kind_order as _measurement_kind_order_fn,
)


class MeasurementListManager:
    def __init__(
        self,
        *,
        all_list,
        distance_list,
        diameter_list,
        radius_list,
        angle_list,
        edit_stack,
        add_type_picker_page_index: int,
        translate: Callable,
        ensure_uid: Callable,
        normalize_distance: Callable,
        normalize_diameter: Callable,
        normalize_radius: Callable,
        normalize_angle: Callable,
        on_cancel_pick: Callable,
        on_refresh_preview: Callable,
        on_update_mode_controls: Callable,
        on_populate_distance_form: Callable,
        on_populate_diameter_form: Callable,
        on_populate_radius_form: Callable,
        on_populate_angle_form: Callable,
        on_start_distance_pick: Callable,
        on_auto_start_diameter_pick: Callable,
        on_clear_current_refs: Callable,
        get_current_distance_item: Callable,
        set_current_distance_item: Callable,
        get_current_diameter_item: Callable,
        set_current_diameter_item: Callable,
        get_current_radius_item: Callable,
        set_current_radius_item: Callable,
        get_current_angle_item: Callable,
        set_current_angle_item: Callable,
        get_add_type_cancel_btn: Callable,
    ):
        self._all_list = all_list
        self._distance_list = distance_list
        self._diameter_list = diameter_list
        self._radius_list = radius_list
        self._angle_list = angle_list
        self._edit_stack = edit_stack
        self._add_type_picker_page_index = add_type_picker_page_index
        self._t = translate
        self._ensure_uid = ensure_uid
        self._normalize_distance = normalize_distance
        self._normalize_diameter = normalize_diameter
        self._normalize_radius = normalize_radius
        self._normalize_angle = normalize_angle
        self._on_cancel_pick = on_cancel_pick
        self._on_refresh_preview = on_refresh_preview
        self._on_update_mode_controls = on_update_mode_controls
        self._on_populate_distance_form = on_populate_distance_form
        self._on_populate_diameter_form = on_populate_diameter_form
        self._on_populate_radius_form = on_populate_radius_form
        self._on_populate_angle_form = on_populate_angle_form
        self._on_start_distance_pick = on_start_distance_pick
        self._on_auto_start_diameter_pick = on_auto_start_diameter_pick
        self._on_clear_current_refs = on_clear_current_refs
        self._get_current_distance_item = get_current_distance_item
        self._set_current_distance_item = set_current_distance_item
        self._get_current_diameter_item = get_current_diameter_item
        self._set_current_diameter_item = set_current_diameter_item
        self._get_current_radius_item = get_current_radius_item
        self._set_current_radius_item = set_current_radius_item
        self._get_current_angle_item = get_current_angle_item
        self._set_current_angle_item = set_current_angle_item
        self._get_add_type_cancel_btn = get_add_type_cancel_btn

        self._pending_add_return_meta: dict | None = None

    # ─────────────────────────────────────────────────────────────────
    # Kind utilities
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def kind_order() -> tuple[str, ...]:
        return _measurement_kind_order_fn()

    def list_for_kind(self, kind: str) -> QListWidget | None:
        return {
            'length': self._distance_list,
            'diameter': self._diameter_list,
            'radius': self._radius_list,
            'angle': self._angle_list,
        }.get(kind)

    def selected_meta(self) -> dict | None:
        item = self._all_list.currentItem()
        if item is None:
            return None
        meta = item.data(Qt.UserRole)
        return meta if isinstance(meta, dict) else None

    @staticmethod
    def find_item_by_uid(src_list: QListWidget, uid: str) -> tuple[int, QListWidgetItem | None]:
        return _find_item_by_uid_fn(src_list, uid)

    # ─────────────────────────────────────────────────────────────────
    # Rebuild / name update
    # ─────────────────────────────────────────────────────────────────

    def rebuild_all_list(
        self,
        preferred_kind: str | None = None,
        preferred_uid: str | None = None,
    ) -> None:
        preferred_kind = str(preferred_kind or '').strip().lower()
        preferred_uid = str(preferred_uid or '').strip()
        self._all_list.blockSignals(True)
        self._all_list.clear()

        for kind in self.kind_order():
            src_list = self.list_for_kind(kind)
            if src_list is None:
                continue
            for row in range(src_list.count()):
                src_item = src_list.item(row)
                data = dict(src_item.data(Qt.UserRole) or {})
                uid = self._ensure_uid(data)
                data['_uid'] = uid
                src_item.setData(Qt.UserRole, data)
                list_item = QListWidgetItem(str(data.get('name') or 'Unnamed'))
                list_item.setData(Qt.UserRole, {'kind': kind, 'uid': uid})
                self._all_list.addItem(list_item)

        self._all_list.blockSignals(False)

        if self._all_list.count() <= 0:
            self._on_clear_current_refs()
            self._edit_stack.setCurrentIndex(0)
            self._on_update_mode_controls()
            return

        if preferred_uid and preferred_kind:
            for idx in range(self._all_list.count()):
                item = self._all_list.item(idx)
                meta = item.data(Qt.UserRole) or {}
                if str(meta.get('kind')) == preferred_kind and str(meta.get('uid')) == preferred_uid:
                    self._all_list.setCurrentRow(idx)
                    return

        self._all_list.setCurrentRow(0)

    def update_name_in_all_list(self, kind: str, uid: str, name: str) -> None:
        for idx in range(self._all_list.count()):
            item = self._all_list.item(idx)
            meta = item.data(Qt.UserRole) or {}
            if str(meta.get('kind')) == str(kind) and str(meta.get('uid')) == str(uid):
                item.setText(str(name or 'Unnamed'))
                return

    # ─────────────────────────────────────────────────────────────────
    # All-list selection dispatch
    # ─────────────────────────────────────────────────────────────────

    def on_all_measurement_selected(self) -> None:
        meta = self.selected_meta()
        self._on_cancel_pick()

        cancel_btn = self._get_add_type_cancel_btn()
        if not meta:
            if cancel_btn is not None:
                cancel_btn.setVisible(False)
            self._on_clear_current_refs()
            self._edit_stack.setCurrentIndex(0)
            self._on_update_mode_controls()
            return

        if cancel_btn is not None:
            cancel_btn.setVisible(False)
        kind = str(meta.get('kind') or '').strip().lower()
        uid = str(meta.get('uid') or '').strip()
        src_list = self.list_for_kind(kind)
        if src_list is None:
            self._edit_stack.setCurrentIndex(0)
            self._on_update_mode_controls()
            return

        _, src_item = self.find_item_by_uid(src_list, uid)
        if src_item is None:
            self.rebuild_all_list()
            return

        for other_kind in self.kind_order():
            other_list = self.list_for_kind(other_kind)
            if other_list is None:
                continue
            other_list.blockSignals(True)
            if other_kind == kind:
                other_list.setCurrentItem(src_item)
            else:
                other_list.clearSelection()
            other_list.blockSignals(False)

        self._on_clear_current_refs()
        if kind == 'length':
            self._set_current_distance_item(src_item)
            self._on_populate_distance_form(src_item.data(Qt.UserRole))
            self._edit_stack.setCurrentIndex(1)
            meas = dict(src_item.data(Qt.UserRole) or {})
            if not str(meas.get('start_xyz') or '').strip() or not str(meas.get('end_xyz') or '').strip():
                self._on_start_distance_pick(False)
        elif kind == 'diameter':
            self._set_current_diameter_item(src_item)
            self._on_populate_diameter_form(src_item.data(Qt.UserRole))
            self._edit_stack.setCurrentIndex(2)
            self._on_auto_start_diameter_pick()
        elif kind == 'radius':
            self._set_current_radius_item(src_item)
            self._on_populate_radius_form(src_item.data(Qt.UserRole))
            self._edit_stack.setCurrentIndex(3)
        elif kind == 'angle':
            self._set_current_angle_item(src_item)
            self._on_populate_angle_form(src_item.data(Qt.UserRole))
            self._edit_stack.setCurrentIndex(4)
        else:
            self._edit_stack.setCurrentIndex(0)

        self._on_update_mode_controls()

    # ─────────────────────────────────────────────────────────────────
    # Add / remove
    # ─────────────────────────────────────────────────────────────────

    def add_of_kind(self, kind: str) -> None:
        normalized = str(kind or '').strip().lower()
        self._pending_add_return_meta = None
        cancel_btn = self._get_add_type_cancel_btn()
        if cancel_btn is not None:
            cancel_btn.setVisible(False)
        if normalized == 'length':
            new_item = self._add_distance()
        elif normalized == 'diameter':
            new_item = self._add_diameter()
        elif normalized == 'radius':
            new_item = self._add_radius()
        elif normalized == 'angle':
            new_item = self._add_angle()
        else:
            return

        data = dict(new_item.data(Qt.UserRole) or {})
        self.rebuild_all_list(preferred_kind=normalized, preferred_uid=str(data.get('_uid') or ''))

    def cancel_add_type_picker(self) -> None:
        self._on_cancel_pick()
        cancel_btn = self._get_add_type_cancel_btn()
        if cancel_btn is not None:
            cancel_btn.setVisible(False)
        meta = dict(self._pending_add_return_meta or {})
        self._pending_add_return_meta = None
        if meta:
            self.rebuild_all_list(
                preferred_kind=str(meta.get('kind') or '').strip().lower(),
                preferred_uid=str(meta.get('uid') or '').strip(),
            )
            return
        if self._all_list.count() > 0:
            self._all_list.setCurrentRow(0)
        else:
            self._edit_stack.setCurrentIndex(0)
            self._on_update_mode_controls()

    def show_add_type_picker(self) -> None:
        self._on_cancel_pick()
        current_meta = self.selected_meta()
        self._pending_add_return_meta = dict(current_meta) if current_meta else None
        self._all_list.clearSelection()
        self._on_clear_current_refs()
        self._edit_stack.setCurrentIndex(self._add_type_picker_page_index)
        self._on_update_mode_controls()
        cancel_btn = self._get_add_type_cancel_btn()
        if cancel_btn is not None:
            cancel_btn.setVisible(True)

    def remove_current(self) -> None:
        meta = self.selected_meta()
        if not meta:
            return

        kind = str(meta.get('kind') or '').strip().lower()
        uid = str(meta.get('uid') or '').strip()
        src_list = self.list_for_kind(kind)
        if src_list is None:
            return

        visual_row = self._all_list.currentRow()
        row, item = self.find_item_by_uid(src_list, uid)
        if item is None or row < 0:
            return

        src_list.takeItem(row)
        self._on_cancel_pick()
        if kind == 'length':
            self._set_current_distance_item(None)
        elif kind == 'diameter':
            self._set_current_diameter_item(None)
        elif kind == 'radius':
            self._set_current_radius_item(None)
        elif kind == 'angle':
            self._set_current_angle_item(None)

        self._on_refresh_preview()
        self.rebuild_all_list()
        if self._all_list.count() > 0:
            self._all_list.setCurrentRow(max(0, min(visual_row, self._all_list.count() - 1)))
        else:
            self._edit_stack.setCurrentIndex(0)
            self._on_update_mode_controls()

    # ─────────────────────────────────────────────────────────────────
    # Populate from tool data
    # ─────────────────────────────────────────────────────────────────

    def populate_from_tool_data(self, tool_data: dict) -> None:
        self._distance_list.clear()
        for meas in tool_data.get('distance_measurements', []):
            normalized = self._normalize_distance(meas)
            item = QListWidgetItem(normalized.get('name', 'Unnamed'))
            item.setData(Qt.UserRole, normalized)
            self._distance_list.addItem(item)

        self._diameter_list.clear()
        for meas in tool_data.get('diameter_measurements', []):
            normalized = self._normalize_diameter(meas)
            item = QListWidgetItem(normalized.get('name', 'Unnamed'))
            item.setData(Qt.UserRole, normalized)
            self._diameter_list.addItem(item)

        self._radius_list.clear()
        for meas in tool_data.get('radius_measurements', []):
            normalized = self._normalize_radius(meas)
            item = QListWidgetItem(normalized.get('name', 'Unnamed'))
            item.setData(Qt.UserRole, normalized)
            self._radius_list.addItem(item)

        self._angle_list.clear()
        for meas in tool_data.get('angle_measurements', []):
            normalized = self._normalize_angle(meas)
            item = QListWidgetItem(normalized.get('name', 'Unnamed'))
            item.setData(Qt.UserRole, normalized)
            self._angle_list.addItem(item)

        self.rebuild_all_list()

    # ─────────────────────────────────────────────────────────────────
    # Add-kind implementations
    # ─────────────────────────────────────────────────────────────────

    def _add_distance(self) -> QListWidgetItem:
        new_meas = {
            'name': self._t('tool_editor.measurements.new_distance', 'New Distance'),
            'start_part': '',
            'start_part_index': -1,
            'start_xyz': '',
            'start_space': 'world',
            'end_part': '',
            'end_part_index': -1,
            'end_xyz': '',
            'end_space': 'world',
            'distance_axis': 'z',
            'label_value_mode': 'measured',
            'label_custom_value': '',
            'type': 'distance',
            '_uid': self._ensure_uid({}),
        }
        item = QListWidgetItem(new_meas['name'])
        item.setData(Qt.UserRole, new_meas)
        self._distance_list.addItem(item)
        self._distance_list.setCurrentItem(item)
        self._on_refresh_preview()
        self._on_start_distance_pick(True)
        return item

    def _add_diameter(self) -> QListWidgetItem:
        new_meas = {
            'name': self._t('tool_editor.measurements.new_diameter', 'New Diameter'),
            'part': '',
            'part_index': -1,
            'center_xyz': '',
            'edge_xyz': '',
            'axis_xyz': '0, 0, 1',
            'diameter_axis_mode': 'z',
            'offset_xyz': '',
            'diameter_visual_offset_mm': 1.0,
            'diameter_mode': 'manual',
            'diameter': '',
            'type': 'diameter_ring',
            '_uid': self._ensure_uid({}),
        }
        item = QListWidgetItem(new_meas['name'])
        item.setData(Qt.UserRole, new_meas)
        self._diameter_list.addItem(item)
        self._diameter_list.setCurrentItem(item)
        self._on_refresh_preview()
        return item

    def _add_radius(self) -> QListWidgetItem:
        new_meas = {
            'name': self._t('tool_editor.measurements.new_radius', 'New Radius'),
            'part': '',
            'center_xyz': '0, 0, 0',
            'axis_xyz': '0, 1, 0',
            'radius': '5',
            'type': 'radius',
            '_uid': self._ensure_uid({}),
        }
        item = QListWidgetItem(new_meas['name'])
        item.setData(Qt.UserRole, new_meas)
        self._radius_list.addItem(item)
        self._radius_list.setCurrentItem(item)
        self._on_refresh_preview()
        return item

    def _add_angle(self) -> QListWidgetItem:
        new_meas = {
            'name': self._t('tool_editor.measurements.new_angle', 'New Angle'),
            'part': '',
            'center_xyz': '0, 0, 0',
            'start_xyz': '1, 0, 0',
            'end_xyz': '0, 1, 0',
            'type': 'angle',
            '_uid': self._ensure_uid({}),
        }
        item = QListWidgetItem(new_meas['name'])
        item.setData(Qt.UserRole, new_meas)
        self._angle_list.addItem(item)
        self._angle_list.setCurrentItem(item)
        self._on_refresh_preview()
        return item


__all__ = ["MeasurementListManager"]
