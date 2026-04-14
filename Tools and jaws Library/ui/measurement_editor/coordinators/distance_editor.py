"""Distance measurement editor coordinator.

Owns distance-specific state (edit_model, axis value, active adjust axis)
and all distance-specific commit/setter/nudge logic. Cross-cutting pick state
(_pick_target / _dist_pick_stage) remains on the dialog and is accessed via
the callbacks injected here.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QLineEdit, QListWidgetItem

from ..controllers.distance_controller import (
    distance_adjust_target_key as _distance_adjust_target_key_helper,
    distance_axis_sign as _distance_axis_sign_helper,
    distance_effective_point_xyz_text as _distance_effective_point_xyz_text_helper,
    distance_measured_value_text as _distance_measured_value_text_helper,
    distance_value_mode as _distance_value_mode_helper,
    normalize_distance_adjust_mode as _normalize_distance_adjust_mode_helper,
    normalize_distance_axis as _normalize_distance_axis_helper,
    normalize_distance_nudge_point as _normalize_distance_nudge_point_helper,
    toggle_distance_adjust_mode as _toggle_distance_adjust_mode_helper,
)
from ..models.distance import compose_distance_commit_payload as _compose_distance_commit_payload
from ..utils.coordinates import xyz_to_tuple as _xyz_to_tuple, fmt_coord as _fmt_coord
from ..utils.edit_helpers import (
    set_xyz_edits as _set_xyz_edits,
    xyz_text_from_edits as _xyz_text_from_edits,
    focused_axis as _focused_axis,
)


class DistanceEditorCoordinator:
    def __init__(
        self,
        refs,
        translate: Callable,
        icon: Callable,
        precise_mode_enabled: Callable,
        get_pick_target: Callable,
        set_pick_target: Callable,
        set_pick_stage: Callable,
        cancel_pick: Callable,
        ensure_uid: Callable,
        on_commit_done: Callable,
        on_name_changed: Callable,
        on_axis_overlay_sync: Callable,
        on_edit_mode_title_update: Callable,
        on_update_measured_value: Callable,
        preview_widget,
        distance_list,
        get_current_item: Callable,
        get_focus_widget: Callable,
    ):
        self._refs = refs
        self._t = translate
        self._icon = icon
        self._precise_mode_enabled = precise_mode_enabled
        self._get_pick_target = get_pick_target
        self._set_pick_target = set_pick_target
        self._set_pick_stage = set_pick_stage
        self._cancel_pick = cancel_pick
        self._ensure_uid = ensure_uid
        self._on_commit_done = on_commit_done
        self._on_name_changed = on_name_changed
        self._on_axis_overlay_sync = on_axis_overlay_sync
        self._on_edit_mode_title_update = on_edit_mode_title_update
        self._on_update_measured_value = on_update_measured_value
        self.preview_widget = preview_widget
        self._distance_list = distance_list
        self._get_current_item = get_current_item
        self._get_focus_widget = get_focus_widget

        self.edit_model: dict | None = None
        self._axis_value = 'z'
        self._adjust_active_axis = 'x'

    # ─────────────────────────────────────────────────────────────────
    # Simple getters
    # ─────────────────────────────────────────────────────────────────

    @property
    def axis_value(self) -> str:
        return self._axis_value

    @property
    def adjust_active_axis(self) -> str:
        return self._adjust_active_axis

    @adjust_active_axis.setter
    def adjust_active_axis(self, value: str) -> None:
        self._adjust_active_axis = value

    def value_mode(self) -> str:
        return _distance_value_mode_helper(self._refs.value_mode_btn.isChecked())

    def adjust_mode(self) -> str:
        return _normalize_distance_adjust_mode_helper('point' if self._refs.adjust_mode_btn.isChecked() else 'offset')

    def nudge_point(self) -> str:
        return _normalize_distance_nudge_point_helper('end' if self._refs.nudge_point_btn.isChecked() else 'start')

    def adjust_edits(self) -> tuple[QLineEdit, QLineEdit, QLineEdit]:
        return self._refs.adjust_x_edit, self._refs.adjust_y_edit, self._refs.adjust_z_edit

    def adjust_target_key(self, mode: str | None = None, point: str | None = None) -> str:
        effective_mode = mode or self.adjust_mode()
        effective_point = point or self.nudge_point()
        return _distance_adjust_target_key_helper(effective_mode, effective_point)

    def adjust_active_axis_value(self) -> str:
        focused = _focused_axis(self.adjust_edits())
        if focused in {'x', 'y', 'z'}:
            self._adjust_active_axis = focused
            return focused
        focus_widget = self._get_focus_widget()
        if focus_widget in {self._refs.nudge_minus_btn, self._refs.nudge_plus_btn}:
            return self._adjust_active_axis
        return 'all'

    def axis_sign(self, model: dict, axis: str) -> float:
        return _distance_axis_sign_helper(model, axis)

    def effective_point_xyz_text(self, point: str) -> str:
        return _distance_effective_point_xyz_text_helper(self.edit_model or {}, point)

    def measured_value_text(self) -> str:
        return _distance_measured_value_text_helper(self.edit_model or {}, self.axis_value)

    # ─────────────────────────────────────────────────────────────────
    # Setters
    # ─────────────────────────────────────────────────────────────────

    def set_value_mode(self, mode: str, commit: bool = True) -> None:
        normalized = mode if mode in {'measured', 'custom'} else 'measured'
        is_custom = normalized == 'custom'
        self._refs.value_mode_btn.blockSignals(True)
        self._refs.value_mode_btn.setChecked(is_custom)
        if is_custom:
            self._refs.value_mode_btn.setText(self._t('tool_editor.measurements.value_mode_custom', 'Custom'))
        else:
            self._refs.value_mode_btn.setText(self._t('tool_editor.measurements.value_mode_measured', 'Measured'))
        self._refs.value_mode_btn.blockSignals(False)
        self._refs.value_edit.setReadOnly(not is_custom)
        self.update_measured_value_box()
        if commit:
            self.commit_edit()

    def on_value_mode_toggled(self) -> None:
        is_custom = self._refs.value_mode_btn.isChecked()
        if is_custom:
            self._refs.value_mode_btn.setText(self._t('tool_editor.measurements.value_mode_custom', 'Custom'))
        else:
            self._refs.value_mode_btn.setText(self._t('tool_editor.measurements.value_mode_measured', 'Measured'))
        self._refs.value_edit.setReadOnly(not is_custom)
        self.update_measured_value_box()
        self.commit_edit()

    def set_axis(self, axis: str, commit: bool = True) -> None:
        normalized = _normalize_distance_axis_helper(axis)
        self._axis_value = normalized
        if self.edit_model is not None:
            self.edit_model['distance_axis'] = normalized
        self._on_axis_overlay_sync()
        if commit:
            self.commit_edit()

    def set_adjust_mode(self, mode: str, commit: bool = True) -> None:
        normalized = _normalize_distance_adjust_mode_helper(mode)
        self._refs.adjust_mode_btn.blockSignals(True)
        self._refs.adjust_mode_btn.setChecked(normalized == 'point')
        self._refs.adjust_mode_btn.blockSignals(False)
        self.update_adjust_controls(refresh_values=True)
        if commit:
            self.commit_edit()

    def on_adjust_mode_toggled(self) -> None:
        previous_mode = _toggle_distance_adjust_mode_helper(self.adjust_mode())
        previous_target = self.adjust_target_key(mode=previous_mode, point=self.nudge_point())
        self.store_adjust_edits_to_model(previous_target)
        self.update_adjust_controls(refresh_values=True)
        self.commit_edit(sync_adjust_edits=False)

    def set_nudge_point(self, point: str, commit: bool = True) -> None:
        normalized = _normalize_distance_nudge_point_helper(point)
        self._refs.nudge_point_btn.blockSignals(True)
        self._refs.nudge_point_btn.setChecked(normalized == 'end')
        self._refs.nudge_point_btn.blockSignals(False)
        self.update_adjust_controls(refresh_values=True)
        if commit:
            self.commit_edit()

    def on_nudge_point_toggled(self) -> None:
        previous_point = 'start' if self.nudge_point() == 'end' else 'end'
        previous_target = self.adjust_target_key(mode='point', point=previous_point)
        self.store_adjust_edits_to_model(previous_target)
        self.update_adjust_controls(refresh_values=True)
        self.commit_edit(sync_adjust_edits=False)

    # ─────────────────────────────────────────────────────────────────
    # Tooltips and control visual state
    # ─────────────────────────────────────────────────────────────────

    def update_adjust_tooltips(self) -> None:
        if self.adjust_mode() == 'point':
            tooltip = self._t(
                'tool_editor.measurements.point_nudge_tooltip',
                'Edit the selected point coordinates. Focus X, Y, or Z, then use + or -.'
            )
        else:
            tooltip = self._t(
                'tool_editor.measurements.offset_tooltip',
                'Drag the arrow in the preview, or type here to fine-tune'
            )
        for axis_edit in self.adjust_edits():
            axis_edit.setToolTip(tooltip)

    def update_adjust_controls(self, refresh_values: bool = True) -> None:
        is_point_mode = self.adjust_mode() == 'point'
        self._refs.adjust_mode_btn.blockSignals(True)
        self._refs.adjust_mode_btn.setChecked(is_point_mode)
        self._refs.adjust_mode_btn.setText('')
        self._refs.adjust_mode_btn.setIcon(self._icon('edit_arrow.svg' if is_point_mode else 'fine_tune.svg'))
        self._refs.adjust_mode_btn.setToolTip(
            self._t('tool_editor.measurements.arrow_offset', 'Arrow offset')
            if is_point_mode else self._t('tool_editor.measurements.nudge', 'Nudge')
        )
        self._refs.adjust_mode_btn.blockSignals(False)
        self._refs.nudge_point_btn.setVisible(is_point_mode)
        is_end = self.nudge_point() == 'end'
        self._refs.nudge_point_btn.setText('')
        self._refs.nudge_point_btn.setIcon(self._icon('end_point.svg' if is_end else 'start_point.svg'))
        self._refs.nudge_point_btn.setToolTip(
            self._t('tool_editor.measurements.click_edit_start_point', 'Click to edit start point')
            if is_end else
            self._t('tool_editor.measurements.click_edit_end_point', 'Click to edit end point')
        )
        self._on_edit_mode_title_update()
        if refresh_values:
            self.load_adjust_edits_from_model()

    def load_adjust_edits_from_model(self) -> None:
        model = self.edit_model or {}
        if self.adjust_mode() == 'point':
            value = self.effective_point_xyz_text(self.nudge_point())
        else:
            value = model.get(self.adjust_target_key(), '0, 0, 0')
        _set_xyz_edits(self.adjust_edits(), value)
        self.update_adjust_tooltips()

    def store_adjust_edits_to_model(self, target_key: str | None = None) -> None:
        if self.edit_model is None:
            return
        self.edit_model[target_key or self.adjust_target_key()] = _xyz_text_from_edits(self.adjust_edits())

    # ─────────────────────────────────────────────────────────────────
    # Measured value / pick status boxes
    # ─────────────────────────────────────────────────────────────────

    def update_measured_value_box(self) -> None:
        mode = self.value_mode()
        if mode == 'measured':
            text = self.measured_value_text()
            self._refs.value_edit.setText(text)
        else:
            custom_text = str(self.edit_model.get('label_custom_value', '') if self.edit_model else '')
            self._refs.value_edit.setText(custom_text)

        current_item = self._get_current_item()
        if current_item is None:
            return

        index = self._distance_list.row(current_item)
        if index < 0:
            return

        if mode == 'measured' and hasattr(self.preview_widget, 'get_distance_measured_value'):
            def _apply_measured_value(value):
                current = self._get_current_item()
                if current is None:
                    return
                if self._distance_list.row(current) != index:
                    return
                try:
                    measured = float(value)
                except (TypeError, ValueError):
                    return
                self._refs.value_edit.setText(f"{measured:.3f} mm")

            self.preview_widget.get_distance_measured_value(index, _apply_measured_value)

    def update_pick_status(self) -> None:
        model = self.edit_model or {}
        has_start = bool(str(model.get('start_xyz') or '').strip())
        has_end = bool(str(model.get('end_xyz') or '').strip())
        self.update_measured_value_box()
        pt = self._get_pick_target()
        if pt and pt.startswith('target_xyz:start'):
            self._refs.pick_status_label.setText(
                self._t('tool_editor.measurements.pick_start_status', 'Click start point in preview')
            )
        elif pt and pt.startswith('target_xyz:end'):
            self._refs.pick_status_label.setText(
                self._t('tool_editor.measurements.pick_end_status', 'Click end point in preview')
            )
        elif has_start and has_end:
            self._refs.pick_status_label.setText(
                self._t('tool_editor.measurements.points_set', 'Start and end points set')
            )
        elif has_start:
            self._refs.pick_status_label.setText(
                self._t('tool_editor.measurements.start_set', 'Start point set, end point missing')
            )
        else:
            self._refs.pick_status_label.setText(
                self._t('tool_editor.measurements.points_missing', 'No points set yet')
            )

    # ─────────────────────────────────────────────────────────────────
    # Pick flow + commit
    # ─────────────────────────────────────────────────────────────────

    def start_two_point_pick(self, reset_points: bool) -> None:
        current_item = self._get_current_item()
        if not current_item:
            return
        if self.edit_model is None:
            self.edit_model = dict(current_item.data(Qt.UserRole) or {})

        if reset_points:
            self.edit_model['start_part'] = ''
            self.edit_model['start_part_index'] = -1
            self.edit_model['start_xyz'] = ''
            self.edit_model['start_space'] = 'world'
            self.edit_model['end_part'] = ''
            self.edit_model['end_part_index'] = -1
            self.edit_model['end_xyz'] = ''
            self.edit_model['end_space'] = 'world'

        self._set_pick_target('target_xyz:start:all')
        self._set_pick_stage('start')
        self.preview_widget.set_point_picking_enabled(True)
        self._on_axis_overlay_sync()
        self._refs.pick_points_btn.setText('')
        self._refs.pick_points_btn.setIcon(self._icon('cancel.svg'))
        self._refs.pick_points_btn.setIconSize(QSize(24, 24))
        self._refs.pick_points_btn.setToolTip(self._t('common.cancel', 'Cancel'))
        self.update_pick_status()

    def commit_edit(self, sync_adjust_edits: bool = True) -> None:
        current_item = self._get_current_item()
        if not current_item:
            return
        if self.edit_model is None:
            self.edit_model = dict(current_item.data(Qt.UserRole) or {})
        model = self.edit_model
        uid = self._ensure_uid(model)
        if sync_adjust_edits:
            self.store_adjust_edits_to_model()
        mode = self.value_mode()
        custom_text = self._refs.value_edit.text().strip() if mode == 'custom' else ''
        meas = _compose_distance_commit_payload(
            model=model,
            name_text=self._refs.name_edit.text(),
            distance_axis=self.axis_value,
            label_value_mode=mode,
            label_custom_value=custom_text,
            uid=uid,
            translate=self._t,
        )
        self.edit_model = dict(meas)
        current_item.setData(Qt.UserRole, meas)
        current_item.setText(meas['name'])
        self._on_name_changed('length', uid, meas['name'])
        self._on_commit_done()
        self.update_pick_status()

    def on_point_nudge(self, direction: str) -> None:
        current_item = self._get_current_item()
        if not current_item or self.edit_model is None:
            return

        nudge_axis = self.adjust_active_axis_value()
        if nudge_axis not in {'x', 'y', 'z'}:
            return

        try:
            step = float(self._refs.nudge_step_edit.text().strip().replace(',', '.')) or 1.0
        except (ValueError, AttributeError):
            step = 1.0

        self.store_adjust_edits_to_model()
        delta = step if direction == '+' else -step
        point_key = self.adjust_target_key()

        x, y, z = _xyz_to_tuple(self.edit_model.get(point_key, '0, 0, 0'))
        if nudge_axis == 'x':
            x += delta
        elif nudge_axis == 'y':
            y += delta
        elif nudge_axis == 'z':
            z += delta

        self.edit_model[point_key] = f"{_fmt_coord(x)}, {_fmt_coord(y)}, {_fmt_coord(z)}"
        self.load_adjust_edits_from_model()
        self.update_measured_value_box()
        self.commit_edit(sync_adjust_edits=False)

    def populate_form(self, meas: dict) -> None:
        self.edit_model = dict(meas or {})
        self._refs.name_edit.setText(meas.get('name', ''))
        self.set_axis(str(meas.get('distance_axis', 'z')).lower(), commit=False)
        self.set_value_mode(str(meas.get('label_value_mode', 'measured')).lower(), commit=False)
        self.set_nudge_point('start', commit=False)
        self.set_adjust_mode('offset', commit=False)
        self.load_adjust_edits_from_model()
        self.update_measured_value_box()
        self.update_pick_status()


__all__ = ["DistanceEditorCoordinator"]
