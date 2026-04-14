"""Pick coordinator for the measurement editor.

Owns pick_target / dist_pick_stage / diam_pick_stage state and dispatches
point-picked events to the appropriate editor coordinator. Callback
injection only — the dialog holds no pick state directly.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLineEdit, QPushButton

from ..utils.coordinates import (
    fmt_coord as _fmt_coord,
    xyz_to_tuple as _xyz_to_tuple,
)


class PickCoordinator:
    def __init__(
        self,
        *,
        preview_widget,
        translate: Callable,
        icon: Callable,
        dist_pick_btn: QPushButton,
        diam_pick_btn: QPushButton,
        radius_center_pick_btn: QPushButton,
        angle_center_pick_btn: QPushButton,
        angle_start_pick_btn: QPushButton,
        angle_end_pick_btn: QPushButton,
        radius_center_edits: tuple[QLineEdit, QLineEdit, QLineEdit],
        radius_part_edit: QLineEdit,
        angle_center_edits: tuple[QLineEdit, QLineEdit, QLineEdit],
        angle_start_edits: tuple[QLineEdit, QLineEdit, QLineEdit],
        angle_end_edits: tuple[QLineEdit, QLineEdit, QLineEdit],
        angle_part_edit: QLineEdit,
        diam_value_edit: QLineEdit,
        distance_editor,
        diameter_editor,
        get_current_distance_item: Callable,
        get_current_diameter_item: Callable,
        focused_axis: Callable,
        on_commit_current_edit: Callable,
        on_sync_axis_overlay: Callable,
    ):
        self.preview_widget = preview_widget
        self._t = translate
        self._icon = icon
        self._dist_pick_btn = dist_pick_btn
        self._diam_pick_btn = diam_pick_btn
        self._radius_center_pick_btn = radius_center_pick_btn
        self._angle_center_pick_btn = angle_center_pick_btn
        self._angle_start_pick_btn = angle_start_pick_btn
        self._angle_end_pick_btn = angle_end_pick_btn
        self._radius_center_edits = radius_center_edits
        self._radius_part_edit = radius_part_edit
        self._angle_center_edits = angle_center_edits
        self._angle_start_edits = angle_start_edits
        self._angle_end_edits = angle_end_edits
        self._angle_part_edit = angle_part_edit
        self._diam_value_edit = diam_value_edit
        self._distance_editor = distance_editor
        self._diameter_editor = diameter_editor
        self._get_current_distance_item = get_current_distance_item
        self._get_current_diameter_item = get_current_diameter_item
        self._focused_axis = focused_axis
        self._on_commit_current_edit = on_commit_current_edit
        self._on_sync_axis_overlay = on_sync_axis_overlay

        self.pick_target: str | None = None
        self.dist_pick_stage: str | None = None
        self.diam_pick_stage: str | None = None

    # ─────────────────────────────────────────────────────────────────
    # Pick target starters
    # ─────────────────────────────────────────────────────────────────

    def on_pick_target(self) -> None:
        if self.pick_target and self.pick_target.startswith('target_xyz:'):
            self.cancel()
            return
        self._distance_editor.start_two_point_pick(reset_points=True)

    def on_pick_radius_center(self) -> None:
        if self.pick_target and self.pick_target.startswith('radius_center_xyz'):
            self.cancel()
            return
        self.cancel()
        axis = self._focused_axis(self._radius_center_edits)
        self.pick_target = f'radius_center_xyz:{axis}'
        self.preview_widget.set_point_picking_enabled(True)
        self._radius_center_pick_btn.setText('\u2716')

    def on_pick_angle_center(self) -> None:
        self.start_angle_pick('angle_center_xyz', self._angle_center_pick_btn, self._angle_center_edits)

    def on_pick_angle_start(self) -> None:
        self.start_angle_pick('angle_start_xyz', self._angle_start_pick_btn, self._angle_start_edits)

    def on_pick_angle_end(self) -> None:
        self.start_angle_pick('angle_end_xyz', self._angle_end_pick_btn, self._angle_end_edits)

    def start_angle_pick(
        self,
        target_prefix: str,
        btn: QPushButton,
        edits: tuple[QLineEdit, QLineEdit, QLineEdit],
    ) -> None:
        if self.pick_target and self.pick_target.startswith(target_prefix):
            self.cancel()
            return
        self.cancel()
        axis = self._focused_axis(edits)
        self.pick_target = f'{target_prefix}:{axis}'
        self.preview_widget.set_point_picking_enabled(True)
        btn.setText('\u2716')

    # ─────────────────────────────────────────────────────────────────
    # Cancel
    # ─────────────────────────────────────────────────────────────────

    def cancel(self) -> None:
        self.pick_target = None
        self.dist_pick_stage = None
        self.diam_pick_stage = None
        if self.preview_widget is not None:
            self.preview_widget.set_point_picking_enabled(False)
        pick_label = self._t('tool_editor.measurements.pick', 'Pick')
        if self._dist_pick_btn is not None:
            self._dist_pick_btn.setText('')
            self._dist_pick_btn.setIcon(self._icon('points_select.svg'))
            self._dist_pick_btn.setIconSize(QSize(24, 24))
            self._dist_pick_btn.setToolTip(pick_label)
        if self._diam_pick_btn is not None:
            self._diam_pick_btn.setText('')
            self._diam_pick_btn.setIcon(self._icon('points_select.svg'))
            self._diam_pick_btn.setIconSize(QSize(24, 24))
            self._diam_pick_btn.setToolTip(pick_label)
        if self._radius_center_pick_btn is not None:
            self._radius_center_pick_btn.setText(pick_label)
        if self._angle_center_pick_btn is not None:
            self._angle_center_pick_btn.setText(pick_label)
        if self._angle_start_pick_btn is not None:
            self._angle_start_pick_btn.setText(pick_label)
        if self._angle_end_pick_btn is not None:
            self._angle_end_pick_btn.setText(pick_label)
        self._distance_editor.update_pick_status()
        self._diameter_editor.update_pick_status()
        self._on_sync_axis_overlay()

    # ─────────────────────────────────────────────────────────────────
    # Point-picked dispatch
    # ─────────────────────────────────────────────────────────────────

    def on_point_picked(self, data: dict) -> None:
        target = self.pick_target
        if not target:
            return
        x = data.get('x', 0)
        y = data.get('y', 0)
        z = data.get('z', 0)
        values = {'x': float(x), 'y': float(y), 'z': float(z)}
        local_values = {
            'x': float(data.get('local_x', values['x'])),
            'y': float(data.get('local_y', values['y'])),
            'z': float(data.get('local_z', values['z'])),
        }
        part_name = data.get('partName', '')
        try:
            part_index = int(data.get('partIndex', -1))
        except Exception:
            part_index = -1

        target_parts = target.split(':')
        target_name = target_parts[0] if target_parts else ''
        axis = target_parts[-1] if len(target_parts) >= 2 else 'all'
        if target_name == 'diameter_center':
            axis = 'z'

        def apply_pick_to_edits(edits: tuple[QLineEdit, QLineEdit, QLineEdit]):
            if axis == 'x':
                edits[0].setText(_fmt_coord(values['x']))
                return
            if axis == 'y':
                edits[1].setText(_fmt_coord(values['y']))
                return
            if axis == 'z':
                edits[2].setText(_fmt_coord(values['z']))
                return
            edits[0].setText(_fmt_coord(values['x']))
            edits[1].setText(_fmt_coord(values['y']))
            edits[2].setText(_fmt_coord(values['z']))

        if target_name == 'target_xyz':
            current_item = self._get_current_distance_item()
            if self._distance_editor.edit_model is None:
                self._distance_editor.edit_model = (
                    dict(current_item.data(Qt.UserRole) or {}) if current_item else {}
                )
            model = self._distance_editor.edit_model
            side = 'start'
            parts = target.split(':')
            if len(parts) >= 2 and parts[1] in {'start', 'end'}:
                side = parts[1]
            if part_index >= 0 or str(part_name or '').strip():
                picked = local_values
                side_part = str(part_name or '').strip()
                side_part_index = part_index
                side_space = 'local'
            else:
                picked = values
                side_part = ''
                side_part_index = -1
                side_space = 'world'

            xyz_value = f"{_fmt_coord(picked['x'])}, {_fmt_coord(picked['y'])}, {_fmt_coord(picked['z'])}"
            model[f'{side}_xyz'] = xyz_value
            model[f'{side}_part'] = side_part
            model[f'{side}_part_index'] = side_part_index
            model[f'{side}_space'] = side_space
            if self._distance_editor.adjust_mode() == 'point' and self._distance_editor.nudge_point() == side:
                self._distance_editor.load_adjust_edits_from_model()

            if side == 'start':
                self.pick_target = 'target_xyz:end:all'
                self.dist_pick_stage = 'end'
                self.preview_widget.set_point_picking_enabled(True)
                self._distance_editor.update_pick_status()
            else:
                self.cancel()
            self._distance_editor.commit_edit(sync_adjust_edits=False)
            return

        if target_name == 'diameter_center':
            current_item = self._get_current_diameter_item()
            if self._diameter_editor.edit_model is None:
                self._diameter_editor.edit_model = (
                    dict(current_item.data(Qt.UserRole) or {}) if current_item else {}
                )
            model = self._diameter_editor.edit_model
            picked = local_values if (part_index >= 0 or str(part_name or '').strip()) else values
            center_x, center_y, center_z = _xyz_to_tuple(model.get('center_xyz', '0, 0, 0'))
            center_z = picked['z']
            model['center_xyz'] = (
                f"{_fmt_coord(center_x)}, {_fmt_coord(center_y)}, {_fmt_coord(center_z)}"
            )
            model['edge_xyz'] = ''
            if part_index >= 0 or str(part_name or '').strip():
                model['part'] = str(part_name or '').strip()
                model['part_index'] = part_index
            else:
                model['part'] = ''
                model['part_index'] = -1
            if self._diameter_editor.adjust_target_key() == 'center_xyz':
                self._diameter_editor.load_adjust_edits_from_model()
            if self._diameter_editor.value_mode() == 'measured':
                self._diameter_editor.start_edge_pick()
            else:
                entered = self._diameter_editor.prompt_value_near_cursor()
                model['diameter'] = entered or ''
                if self._diam_value_edit is not None:
                    self._diam_value_edit.setText(model['diameter'])
                self.cancel()
            self._diameter_editor.commit_edit(sync_adjust_edits=False)
            return

        if target_name == 'diameter_edge':
            current_item = self._get_current_diameter_item()
            if self._diameter_editor.edit_model is None:
                self._diameter_editor.edit_model = (
                    dict(current_item.data(Qt.UserRole) or {}) if current_item else {}
                )
            model = self._diameter_editor.edit_model
            expected_part = str(model.get('part') or '').strip()
            try:
                expected_part_index = int(model.get('part_index', -1) or -1)
            except Exception:
                expected_part_index = -1
            if expected_part_index >= 0 or expected_part:
                same_part = (
                    part_index == expected_part_index
                    if expected_part_index >= 0 and part_index >= 0
                    else str(part_name or '').strip() == expected_part
                )
                if not same_part:
                    return
                picked = local_values
            else:
                picked = values
            model['edge_xyz'] = (
                f"{_fmt_coord(picked['x'])}, {_fmt_coord(picked['y'])}, {_fmt_coord(picked['z'])}"
            )
            if self._diameter_editor.adjust_target_key() == 'edge_xyz':
                self._diameter_editor.load_adjust_edits_from_model()
            self.cancel()
            self._diameter_editor.commit_edit(sync_adjust_edits=False)
            return

        if target_name == 'center_xyz':
            self.cancel()
            current_item = self._get_current_diameter_item()
            if self._diameter_editor.edit_model is None:
                self._diameter_editor.edit_model = (
                    dict(current_item.data(Qt.UserRole) or {}) if current_item else {}
                )
            model = self._diameter_editor.edit_model
            picked = local_values if (part_index >= 0 or str(part_name or '').strip()) else values
            current_x, current_y, current_z = _xyz_to_tuple(model.get('center_xyz', '0, 0, 0'))
            if axis == 'x':
                current_x = picked['x']
            elif axis == 'y':
                current_y = picked['y']
            elif axis == 'z':
                current_z = picked['z']
            else:
                current_x, current_y, current_z = picked['x'], picked['y'], picked['z']
            model['center_xyz'] = f"{_fmt_coord(current_x)}, {_fmt_coord(current_y)}, {_fmt_coord(current_z)}"
            model['part'] = str(part_name or '').strip() if (part_index >= 0 or str(part_name or '').strip()) else ''
            model['part_index'] = part_index if (part_index >= 0 or str(part_name or '').strip()) else -1
        elif target_name == 'radius_center_xyz':
            self.cancel()
            apply_pick_to_edits(self._radius_center_edits)
            if part_name:
                self._radius_part_edit.setText(part_name)
        elif target_name == 'angle_center_xyz':
            self.cancel()
            apply_pick_to_edits(self._angle_center_edits)
            if part_name:
                self._angle_part_edit.setText(part_name)
        elif target_name == 'angle_start_xyz':
            self.cancel()
            apply_pick_to_edits(self._angle_start_edits)
            if part_name:
                self._angle_part_edit.setText(part_name)
        elif target_name == 'angle_end_xyz':
            self.cancel()
            apply_pick_to_edits(self._angle_end_edits)
            if part_name:
                self._angle_part_edit.setText(part_name)
        else:
            self.cancel()

        self._on_commit_current_edit()


__all__ = ["PickCoordinator"]
