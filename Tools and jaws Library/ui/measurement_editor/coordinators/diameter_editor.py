"""Diameter measurement editor coordinator.

Owns diameter-specific state (edit_model, axis value, active adjust axis)
and all diameter-specific commit/setter/pick/nudge logic. Cross-cutting
pick state (_pick_target / _diam_pick_stage) remains on the dialog and is
accessed via the callbacks injected here.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QPoint, QSize
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from ..controllers.diameter_controller import (
    diameter_adjust_mode as _diameter_adjust_mode_helper,
    diameter_adjust_target_key as _diameter_adjust_target_key_helper,
    diameter_geometry_target as _diameter_geometry_target_helper,
    diameter_has_manual_value as _diameter_has_manual_value_helper,
    diameter_is_complete as _diameter_is_complete_helper,
    diameter_measured_numeric as _diameter_measured_numeric_helper,
    diameter_visual_offset_mm as _diameter_visual_offset_mm_helper,
    normalize_diameter_adjust_mode as _normalize_diameter_adjust_mode_helper,
    normalize_diameter_geometry_target as _normalize_diameter_geometry_target_helper,
    toggle_diameter_adjust_mode as _toggle_diameter_adjust_mode_helper,
    toggle_diameter_geometry_target as _toggle_diameter_geometry_target_helper,
)
from ..models.diameter import compose_diameter_commit_payload as _compose_diameter_commit_payload
from ..utils.axis_math import (
    axis_xyz_text as _axis_xyz_text,
    axis_xyz_to_rotation_deg_tuple as _axis_xyz_to_rotation_deg_tuple,
    normalize_axis_xyz_text as _normalize_axis_xyz_text,
    normalize_diameter_axis_mode as _normalize_diameter_axis_mode,
    rotation_deg_to_axis_xyz_text as _rotation_deg_to_axis_xyz_text,
)
from ..utils.coordinates import (
    float_or_default as _float_or_default,
    fmt_coord as _fmt_coord,
    xyz_to_tuple as _xyz_to_tuple,
)
from ..utils.edit_helpers import (
    focused_axis as _focused_axis,
    set_xyz_edits as _set_xyz_edits,
    xyz_text_from_edits as _xyz_text_from_edits,
)


class DiameterEditorCoordinator:
    def __init__(
        self,
        refs,
        translate: Callable,
        icon: Callable,
        get_pick_target: Callable,
        set_pick_target: Callable,
        set_pick_stage: Callable,
        cancel_pick: Callable,
        ensure_uid: Callable,
        normalize_measurement: Callable,
        on_commit_done: Callable,
        on_name_changed: Callable,
        on_axis_overlay_sync: Callable,
        on_axis_overlay_buttons_update: Callable,
        on_edit_mode_title_update: Callable,
        preview_widget,
        diameter_list,
        distance_list_count: Callable,
        get_current_item: Callable,
        get_focus_widget: Callable,
        dialog_parent,
        dialog_setup: Callable,
        create_dialog_buttons: Callable,
        apply_secondary_button_theme: Callable,
    ):
        self._refs = refs
        self._t = translate
        self._icon = icon
        self._get_pick_target = get_pick_target
        self._set_pick_target = set_pick_target
        self._set_pick_stage = set_pick_stage
        self._cancel_pick = cancel_pick
        self._ensure_uid = ensure_uid
        self._normalize_measurement = normalize_measurement
        self._on_commit_done = on_commit_done
        self._on_name_changed = on_name_changed
        self._on_axis_overlay_sync = on_axis_overlay_sync
        self._on_axis_overlay_buttons_update = on_axis_overlay_buttons_update
        self._on_edit_mode_title_update = on_edit_mode_title_update
        self.preview_widget = preview_widget
        self._diameter_list = diameter_list
        self._distance_list_count = distance_list_count
        self._get_current_item = get_current_item
        self._get_focus_widget = get_focus_widget
        self._dialog_parent = dialog_parent
        self._dialog_setup = dialog_setup
        self._create_dialog_buttons = create_dialog_buttons
        self._apply_secondary_button_theme = apply_secondary_button_theme

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
        return 'manual' if self._refs.value_mode_btn.isChecked() else 'measured'

    def adjust_mode(self) -> str:
        return _diameter_adjust_mode_helper(self._refs.adjust_mode_btn.isChecked())

    def geometry_target(self) -> str:
        return _diameter_geometry_target_helper(self._axis_value, self._refs.geometry_target_btn.isChecked())

    def adjust_edits(self) -> tuple[QLineEdit, QLineEdit, QLineEdit]:
        return self._refs.adjust_x_edit, self._refs.adjust_y_edit, self._refs.adjust_z_edit

    def adjust_target_key(self, mode: str | None = None, geometry_target: str | None = None) -> str:
        effective_mode = mode or self.adjust_mode()
        effective_target = geometry_target or self.geometry_target()
        return _diameter_adjust_target_key_helper(effective_mode, effective_target)

    def adjust_active_axis_value(self) -> str:
        focused = _focused_axis(self.adjust_edits())
        if focused in {'x', 'y', 'z'}:
            self._adjust_active_axis = focused
            return focused
        focus_widget = self._get_focus_widget()
        if focus_widget in {self._refs.nudge_minus_btn, self._refs.nudge_plus_btn}:
            return self._adjust_active_axis
        return 'all'

    def overlay_index(self) -> int:
        current = self._get_current_item()
        if current is None:
            return -1
        row = self._diameter_list.row(current)
        if row < 0:
            return -1
        return self._distance_list_count() + row

    def measured_numeric(self) -> float | None:
        return _diameter_measured_numeric_helper(self.edit_model or {})

    def visual_offset_mm(self, model: dict | None = None) -> float:
        data = model if model is not None else (self.edit_model or {})
        return _diameter_visual_offset_mm_helper(data)

    def has_manual_value(self, model: dict | None = None) -> bool:
        data = model if model is not None else (self.edit_model or {})
        return _diameter_has_manual_value_helper(data)

    def is_complete(self, model: dict | None = None) -> bool:
        data = model or self.edit_model
        if data is None:
            current = self._get_current_item()
            if current is not None:
                data = dict(current.data(Qt.UserRole) or {})
        return _diameter_is_complete_helper(data or {}, self.value_mode())

    # ─────────────────────────────────────────────────────────────────
    # Setters
    # ─────────────────────────────────────────────────────────────────

    def set_value_mode(self, mode: str, commit: bool = True) -> None:
        normalized = 'manual' if mode == 'manual' else 'measured'
        is_manual = normalized == 'manual'
        self._refs.value_mode_btn.blockSignals(True)
        self._refs.value_mode_btn.setChecked(is_manual)
        self._refs.value_mode_btn.setText(
            self._t('tool_editor.measurements.value_mode_manual', 'Mukautettu')
            if is_manual else
            self._t('tool_editor.measurements.value_mode_measured', 'Mitattu')
        )
        self._refs.value_mode_btn.blockSignals(False)
        if self.edit_model is not None:
            self.edit_model['diameter_mode'] = normalized
        self._refs.value_edit.setReadOnly(not is_manual)
        if is_manual and self._get_pick_target() == 'diameter_edge:all':
            self._cancel_pick()
        self.update_measured_value_box()
        self.update_pick_status()
        self.update_adjust_controls(refresh_values=False)
        self._on_axis_overlay_sync()
        if commit:
            self.commit_edit()
            if not is_manual:
                self.auto_start_pick_if_needed()

    def on_value_mode_toggled(self) -> None:
        self.set_value_mode('manual' if self._refs.value_mode_btn.isChecked() else 'measured', commit=True)

    def set_axis(self, axis: str, commit: bool = True, store_adjust_edits: bool = True) -> None:
        normalized = axis if axis in {'direct', 'x', 'y', 'z'} else 'z'
        if store_adjust_edits:
            previous_target = self.adjust_target_key()
            self.store_adjust_edits_to_model(previous_target)
        self._axis_value = normalized
        if self.edit_model is not None:
            self.edit_model['diameter_axis_mode'] = normalized
            if normalized in {'x', 'y', 'z'}:
                self.edit_model['axis_xyz'] = _axis_xyz_text(normalized)
                rx_deg, ry_deg, rz_deg = _axis_xyz_to_rotation_deg_tuple(self.edit_model['axis_xyz'])
                self.edit_model['_axis_rotation_deg'] = (
                    f"{_fmt_coord(rx_deg)}, {_fmt_coord(ry_deg)}, {_fmt_coord(rz_deg)}"
                )
            else:
                self.edit_model['axis_xyz'] = _normalize_axis_xyz_text(
                    self.edit_model.get('axis_xyz', '0, 0, 1')
                )
                if not str(self.edit_model.get('_axis_rotation_deg') or '').strip():
                    rx_deg, ry_deg, rz_deg = _axis_xyz_to_rotation_deg_tuple(self.edit_model['axis_xyz'])
                    self.edit_model['_axis_rotation_deg'] = (
                        f"{_fmt_coord(rx_deg)}, {_fmt_coord(ry_deg)}, {_fmt_coord(rz_deg)}"
                    )
        if normalized in {'x', 'y', 'z'}:
            self._refs.geometry_target_btn.blockSignals(True)
            self._refs.geometry_target_btn.setChecked(False)
            self._refs.geometry_target_btn.blockSignals(False)
        self._on_axis_overlay_buttons_update()
        self.update_adjust_controls(refresh_values=True)
        self.update_pick_status()
        self.update_measured_value_box()
        self._on_axis_overlay_sync()
        if commit:
            self.commit_edit()

    def set_adjust_mode(self, mode: str, commit: bool = True) -> None:
        normalized = _normalize_diameter_adjust_mode_helper(mode)
        self._refs.adjust_mode_btn.blockSignals(True)
        self._refs.adjust_mode_btn.setChecked(normalized == 'geometry')
        self._refs.adjust_mode_btn.blockSignals(False)
        if normalized == 'geometry' and self.geometry_target() == 'rotation':
            self.ensure_rotation_target_value()
        self.update_adjust_controls(refresh_values=True)
        if commit:
            self.commit_edit(sync_adjust_edits=False)

    def on_adjust_mode_toggled(self) -> None:
        previous_mode = _toggle_diameter_adjust_mode_helper(self.adjust_mode())
        previous_target = self.adjust_target_key(
            mode=previous_mode,
            geometry_target=self.geometry_target(),
        )
        self.store_adjust_edits_to_model(previous_target)
        if self.adjust_mode() == 'geometry' and self.geometry_target() == 'rotation':
            self.ensure_rotation_target_value()
        self.update_adjust_controls(refresh_values=True)
        self.commit_edit(sync_adjust_edits=False)

    def set_geometry_target(self, target: str, commit: bool = True) -> None:
        normalized = _normalize_diameter_geometry_target_helper(target, self._axis_value)
        self._refs.geometry_target_btn.blockSignals(True)
        self._refs.geometry_target_btn.setChecked(normalized == 'rotation')
        self._refs.geometry_target_btn.blockSignals(False)
        if normalized == 'rotation':
            self.ensure_rotation_target_value()
        self.update_adjust_controls(refresh_values=True)
        if commit:
            self.commit_edit(sync_adjust_edits=False)

    def on_geometry_target_toggled(self) -> None:
        previous_target = _toggle_diameter_geometry_target_helper(
            self.geometry_target(),
            self._axis_value,
        )
        previous_target_key = self.adjust_target_key(
            mode='geometry',
            geometry_target=previous_target,
        )
        self.store_adjust_edits_to_model(previous_target_key)
        if self.geometry_target() == 'rotation':
            self.ensure_rotation_target_value()
        self.update_adjust_controls(refresh_values=True)
        self.commit_edit(sync_adjust_edits=False)

    def ensure_rotation_target_value(self) -> None:
        if self.edit_model is None:
            return
        self.edit_model['axis_xyz'] = _normalize_axis_xyz_text(
            self.edit_model.get('axis_xyz', '0, 0, 1')
        )
        if not str(self.edit_model.get('_axis_rotation_deg') or '').strip():
            rx_deg, ry_deg, rz_deg = _axis_xyz_to_rotation_deg_tuple(
                self.edit_model.get('axis_xyz', '0, 0, 1')
            )
            self.edit_model['_axis_rotation_deg'] = (
                f"{_fmt_coord(rx_deg)}, {_fmt_coord(ry_deg)}, {_fmt_coord(rz_deg)}"
            )

    # ─────────────────────────────────────────────────────────────────
    # Visual offset / adjust edits
    # ─────────────────────────────────────────────────────────────────

    def load_visual_offset_from_model(self) -> None:
        if self.edit_model is None:
            return
        self._refs.visual_offset_edit.setText(_fmt_coord(self.visual_offset_mm(self.edit_model)))

    def store_visual_offset_to_model(self) -> None:
        if self.edit_model is None:
            return
        self.edit_model['diameter_visual_offset_mm'] = _float_or_default(
            self._refs.visual_offset_edit.text(),
            1.0,
        )

    def update_adjust_tooltips(self) -> None:
        mode = self.adjust_mode()
        if mode == 'callout':
            tooltip = self._t(
                'tool_editor.measurements.callout_tooltip',
                'Drag the callout in the preview, or type here to fine-tune'
            )
        elif self.geometry_target() == 'rotation':
            tooltip = self._t(
                'tool_editor.measurements.diameter_rotation_tooltip',
                'Edit 3D axis rotation in degrees (X/Y/Z).'
            )
        else:
            tooltip = self._t(
                'tool_editor.measurements.diameter_axis_position_tooltip',
                'Edit center coordinates to move the diameter ring position'
            )
        for axis_edit in self.adjust_edits():
            axis_edit.setToolTip(tooltip)

    def load_adjust_edits_from_model(self) -> None:
        if self.edit_model is None:
            return
        target_key = self.adjust_target_key()
        if target_key == 'axis_xyz':
            rotation_text = str(self.edit_model.get('_axis_rotation_deg') or '').strip()
            if not rotation_text:
                rx_deg, ry_deg, rz_deg = _axis_xyz_to_rotation_deg_tuple(
                    self.edit_model.get('axis_xyz', '0, 0, 1')
                )
                rotation_text = f"{_fmt_coord(rx_deg)}, {_fmt_coord(ry_deg)}, {_fmt_coord(rz_deg)}"
                self.edit_model['_axis_rotation_deg'] = rotation_text
            _set_xyz_edits(self.adjust_edits(), rotation_text)
        else:
            _set_xyz_edits(
                self.adjust_edits(),
                self.edit_model.get(target_key, '0, 0, 0'),
            )
        self.update_adjust_tooltips()
        self.load_visual_offset_from_model()

    def store_adjust_edits_to_model(self, target_key: str | None = None) -> None:
        if self.edit_model is None:
            return
        self.store_visual_offset_to_model()
        key = target_key or self.adjust_target_key()
        value_text = _xyz_text_from_edits(self.adjust_edits())

        if key == 'offset_xyz':
            if not str(self.edit_model.get('offset_xyz') or '').strip():
                ox, oy, oz = _xyz_to_tuple(value_text)
                if abs(ox) <= 1e-6 and abs(oy) <= 1e-6 and abs(oz) <= 1e-6:
                    self.edit_model['offset_xyz'] = ''
                    return
            self.edit_model['offset_xyz'] = value_text
            return

        if key == 'axis_xyz':
            rx_deg, ry_deg, rz_deg = _xyz_to_tuple(value_text)
            self.edit_model['_axis_rotation_deg'] = (
                f"{_fmt_coord(rx_deg)}, {_fmt_coord(ry_deg)}, {_fmt_coord(rz_deg)}"
            )
            self.edit_model['axis_xyz'] = _rotation_deg_to_axis_xyz_text(
                rx_deg,
                ry_deg,
                rz_deg,
                fallback=self.edit_model.get('axis_xyz', '0, 0, 1'),
            )
            return

        if key == 'center_xyz':
            prev_cx, prev_cy, prev_cz = _xyz_to_tuple(self.edit_model.get('center_xyz', '0, 0, 0'))
            next_cx, next_cy, next_cz = _xyz_to_tuple(value_text)
            dx = next_cx - prev_cx
            dy = next_cy - prev_cy
            dz = next_cz - prev_cz
            if abs(dx) > 1e-9 or abs(dy) > 1e-9 or abs(dz) > 1e-9:
                edge_text = str(self.edit_model.get('edge_xyz') or '').strip()
                if edge_text:
                    ex, ey, ez = _xyz_to_tuple(edge_text)
                    self.edit_model['edge_xyz'] = (
                        f"{_fmt_coord(ex + dx)}, {_fmt_coord(ey + dy)}, {_fmt_coord(ez + dz)}"
                    )

        self.edit_model[key] = value_text

    def update_adjust_controls(self, refresh_values: bool = True) -> None:
        is_geometry_mode = self.adjust_mode() == 'geometry'
        rotation_available = self._axis_value == 'direct'
        is_rotation = rotation_available and self.geometry_target() == 'rotation'
        self._refs.adjust_mode_btn.blockSignals(True)
        self._refs.adjust_mode_btn.setChecked(is_geometry_mode)
        self._refs.adjust_mode_btn.setText('')
        self._refs.adjust_mode_btn.setIcon(self._icon('comment.svg' if is_geometry_mode else 'move.svg'))
        self._refs.adjust_mode_btn.setToolTip(
            self._t('tool_editor.measurements.click_edit_callout_position', 'Click to move callout')
            if is_geometry_mode else
            self._t('tool_editor.measurements.click_edit_diameter_geometry', 'Click to edit diameter position')
        )
        self._refs.adjust_mode_btn.blockSignals(False)

        self._refs.geometry_target_btn.blockSignals(True)
        self._refs.geometry_target_btn.setChecked(is_rotation)
        self._refs.geometry_target_btn.setText('')
        self._refs.geometry_target_btn.setIcon(self._icon('move.svg' if is_rotation else 'rotate.svg'))
        self._refs.geometry_target_btn.setToolTip(
            self._t('tool_editor.measurements.click_edit_axis_position', 'Click to edit axis position')
            if is_rotation else
            self._t('tool_editor.measurements.click_edit_diameter_rotation', 'Click to edit rotation around axis')
        )
        self._refs.geometry_target_btn.setVisible(is_geometry_mode and rotation_available)
        self._refs.geometry_target_btn.setEnabled(rotation_available)
        self._refs.geometry_target_btn.blockSignals(False)

        self._refs.adjust_step_unit_lbl.setText('deg' if (is_geometry_mode and is_rotation) else 'mm')
        is_manual_mode = self.value_mode() == 'manual'
        self._refs.visual_offset_edit.setReadOnly(not is_manual_mode)
        self._refs.visual_offset_edit.setEnabled(is_manual_mode)
        self._refs.visual_offset_edit.setToolTip(
            self._t(
                'tool_editor.measurements.diameter_visual_offset_tooltip',
                'Adjust rendered ring size without changing the measured/manual value',
            )
        )
        self._refs.visual_offset_label.setEnabled(is_manual_mode)

        if refresh_values:
            self.load_adjust_edits_from_model()
        self._on_edit_mode_title_update()

    # ─────────────────────────────────────────────────────────────────
    # Measured value / pick status boxes
    # ─────────────────────────────────────────────────────────────────

    def update_measured_value_box(self) -> None:
        mode = self.value_mode()
        if mode == 'measured':
            measured = self.measured_numeric()
            self._refs.value_edit.setText(f"{measured:.3f} mm" if measured is not None else '')
        else:
            custom_text = str(self.edit_model.get('diameter', '') if self.edit_model else '')
            self._refs.value_edit.setText(custom_text)

        current = self._get_current_item()
        if current is None or mode != 'measured':
            return

        index = self.overlay_index()
        if index < 0 or not hasattr(self.preview_widget, 'get_measurement_resolved_value'):
            return

        def _apply_measured_value(value):
            if self._get_current_item() is None:
                return
            if self.overlay_index() != index:
                return
            try:
                measured = float(value)
            except (TypeError, ValueError):
                return
            self._refs.value_edit.setText(f"{measured:.3f} mm")

        self.preview_widget.get_measurement_resolved_value(index, _apply_measured_value)

    def update_pick_status(self) -> None:
        model = self.edit_model or {}
        has_center = bool(str(model.get('center_xyz') or '').strip())
        has_edge = bool(str(model.get('edge_xyz') or '').strip())
        has_value = False
        try:
            has_value = float(str(model.get('diameter', '')).strip().replace(',', '.')) > 1e-6
        except Exception:
            has_value = False
        self.update_measured_value_box()
        pt = self._get_pick_target()
        if pt == 'diameter_center':
            self._refs.pick_status_label.setText(
                self._t('tool_editor.measurements.pick_center_status', 'Click center point on Z axis')
            )
        elif pt == 'diameter_edge:all':
            self._refs.pick_status_label.setText(
                self._t('tool_editor.measurements.pick_edge_status', 'Center set, click edge point')
            )
        elif not has_center:
            self._refs.pick_status_label.setText(
                self._t('tool_editor.measurements.center_missing', 'No center point set yet')
            )
        elif self.value_mode() == 'measured':
            self._refs.pick_status_label.setText(
                self._t('tool_editor.measurements.center_set_edge_missing', 'Center point set, edge point missing')
                if not has_edge else
                self._t('tool_editor.measurements.center_and_diameter_set', 'Center and diameter set')
            )
        else:
            self._refs.pick_status_label.setText(
                self._t('tool_editor.measurements.center_and_diameter_set', 'Center and diameter set')
                if has_value else
                self._t('tool_editor.measurements.center_set_manual', 'Center point set, enter diameter')
            )

    # ─────────────────────────────────────────────────────────────────
    # Manual value prompt
    # ─────────────────────────────────────────────────────────────────

    def prompt_value_near_cursor(self) -> str | None:
        initial_value = 10.0
        if self.has_manual_value():
            try:
                initial_value = float(
                    str((self.edit_model or {}).get('diameter', '')).strip().replace(',', '.')
                )
            except Exception:
                initial_value = 10.0

        dialog = QDialog(self._dialog_parent)
        self._dialog_setup(dialog)
        dialog.setModal(True)
        dialog.setWindowTitle(self._t('tool_editor.measurements.diameter', 'Diameter'))

        root = QVBoxLayout(dialog)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        prompt = QLabel(self._t('tool_editor.measurements.enter_diameter_mm', 'Enter diameter (mm)'))
        prompt.setProperty('detailFieldKey', True)
        prompt.setWordWrap(True)
        root.addWidget(prompt)

        diameter_edit = QLineEdit(dialog)
        diameter_edit.setMinimumWidth(220)
        diameter_edit.setText(f"{max(initial_value, 0.001):.3f}".replace('.', ','))
        root.addWidget(diameter_edit)

        buttons = self._create_dialog_buttons(
            dialog,
            save_text=self._t('common.ok', 'OK'),
            cancel_text=self._t('common.cancel', 'Cancel'),
            on_save=dialog.accept,
            on_cancel=dialog.reject,
        )
        root.addWidget(buttons)
        self._apply_secondary_button_theme(dialog, buttons.button(QDialogButtonBox.Save))

        dialog.adjustSize()
        dialog.move(QCursor.pos() + QPoint(14, 14))
        diameter_edit.setFocus()
        diameter_edit.selectAll()

        if dialog.exec() != QDialog.Accepted:
            return None
        try:
            value = float(str(diameter_edit.text() or '').strip().replace(',', '.'))
        except Exception:
            return None
        if not (value > 1e-6):
            return None
        return f"{value:.6g}"

    # ─────────────────────────────────────────────────────────────────
    # Pick flow
    # ─────────────────────────────────────────────────────────────────

    def start_edge_pick(self) -> None:
        if not self._get_current_item():
            return
        self._set_pick_target('diameter_edge:all')
        self._set_pick_stage('edge')
        self.preview_widget.set_point_picking_enabled(True)
        self._refs.pick_points_btn.setText('')
        self._refs.pick_points_btn.setIcon(self._icon('cancel.svg'))
        self._refs.pick_points_btn.setIconSize(QSize(24, 24))
        self._refs.pick_points_btn.setToolTip(self._t('common.cancel', 'Cancel'))
        self.update_pick_status()
        self._on_axis_overlay_sync()

    def start_pick(self, reset_points: bool) -> None:
        current = self._get_current_item()
        if not current:
            return
        if self.edit_model is None:
            self.edit_model = dict(current.data(Qt.UserRole) or {})
        self.set_axis('z', commit=False, store_adjust_edits=False)
        if reset_points:
            self.edit_model['part'] = ''
            self.edit_model['part_index'] = -1
            self.edit_model['center_xyz'] = ''
            self.edit_model['edge_xyz'] = ''
            self.edit_model['offset_xyz'] = ''
            self.edit_model['diameter_visual_offset_mm'] = 1.0
            self.edit_model['diameter'] = ''
            self.edit_model['diameter_mode'] = 'manual'
            self.set_value_mode('manual', commit=False)
        self._set_pick_target('diameter_center')
        self._set_pick_stage('center')
        self.preview_widget.set_point_picking_enabled(True)
        self._refs.pick_points_btn.setText('')
        self._refs.pick_points_btn.setIcon(self._icon('cancel.svg'))
        self._refs.pick_points_btn.setIconSize(QSize(24, 24))
        self._refs.pick_points_btn.setToolTip(self._t('common.cancel', 'Cancel'))
        self.update_pick_status()
        self._on_axis_overlay_sync()

    def auto_start_pick_if_needed(self) -> None:
        current = self._get_current_item()
        if not current:
            return
        model = self.edit_model or {}
        has_center = bool(str(model.get('center_xyz') or '').strip())
        has_edge = bool(str(model.get('edge_xyz') or '').strip())
        mode = str(model.get('diameter_mode') or self.value_mode()).strip().lower()
        if mode not in {'measured', 'manual'}:
            mode = self.value_mode()
        if not has_center:
            self.start_pick(reset_points=False)
        elif mode == 'measured' and not has_edge:
            self.start_edge_pick()
        else:
            self.update_pick_status()
            self._on_axis_overlay_sync()

    def on_pick_points(self) -> None:
        if self._get_pick_target() in {'diameter_center', 'diameter_edge:all'}:
            self._cancel_pick()
            return
        self.start_pick(reset_points=True)

    # ─────────────────────────────────────────────────────────────────
    # Commit / populate / nudge
    # ─────────────────────────────────────────────────────────────────

    def commit_edit(self, sync_adjust_edits: bool = True) -> None:
        current = self._get_current_item()
        if not current:
            return
        if self.edit_model is None:
            self.edit_model = dict(current.data(Qt.UserRole) or {})
        model = self.edit_model
        uid = self._ensure_uid(model)
        self.store_visual_offset_to_model()
        if sync_adjust_edits:
            self.store_adjust_edits_to_model()
        mode = self.value_mode()
        measured_value = self.measured_numeric() if mode == 'measured' else None
        diameter_text = (
            f"{measured_value:.6g}" if measured_value is not None else ''
        ) if mode == 'measured' else self._refs.value_edit.text().strip()
        meas = _compose_diameter_commit_payload(
            model=model,
            name_text=self._refs.name_edit.text(),
            axis_value=self._axis_value,
            diameter_mode=mode,
            diameter_text=diameter_text,
            visual_offset_mm=self.visual_offset_mm(model),
            uid=uid,
            translate=self._t,
        )
        self.edit_model = dict(meas)
        current.setData(Qt.UserRole, meas)
        current.setText(meas['name'])
        self._on_name_changed('diameter', uid, meas['name'])
        self._on_commit_done()
        self.update_measured_value_box()
        self.update_pick_status()
        self._on_axis_overlay_sync()

    def populate_form(self, meas: dict) -> None:
        self.edit_model = dict(self._normalize_measurement(meas))
        self._refs.name_edit.setText(self.edit_model.get('name', ''))
        self.set_axis(
            _normalize_diameter_axis_mode(
                self.edit_model.get('diameter_axis_mode', ''),
                self.edit_model.get('axis_xyz', '0, 0, 1'),
                default='z',
            ),
            commit=False,
            store_adjust_edits=False,
        )
        self.set_value_mode(str(self.edit_model.get('diameter_mode', 'manual')).lower(), commit=False)
        self.set_geometry_target('axis', commit=False)
        self.set_adjust_mode('callout', commit=False)
        self.update_adjust_controls(refresh_values=True)
        self.update_measured_value_box()
        self.update_pick_status()

    def on_offset_nudge(self, direction: str) -> None:
        current = self._get_current_item()
        if not current or self.edit_model is None:
            return

        nudge_axis = self.adjust_active_axis_value()
        if nudge_axis not in {'x', 'y', 'z'}:
            return

        try:
            step = float(self._refs.nudge_step_edit.text().strip().replace(',', '.')) or 1.0
        except (ValueError, AttributeError):
            step = 1.0

        target_key = self.adjust_target_key()
        self.store_adjust_edits_to_model(target_key)
        delta = step if direction == '+' else -step
        if target_key == 'axis_xyz':
            x, y, z = _xyz_to_tuple(_xyz_text_from_edits(self.adjust_edits()))
        else:
            x, y, z = _xyz_to_tuple(self.edit_model.get(target_key, '0, 0, 0'))
        if nudge_axis == 'x':
            x += delta
        elif nudge_axis == 'y':
            y += delta
        else:
            z += delta

        if target_key == 'axis_xyz':
            rotation_text = f"{_fmt_coord(x)}, {_fmt_coord(y)}, {_fmt_coord(z)}"
            _set_xyz_edits(self.adjust_edits(), rotation_text)
            self.edit_model['_axis_rotation_deg'] = rotation_text
            self.edit_model[target_key] = _rotation_deg_to_axis_xyz_text(
                x,
                y,
                z,
                fallback=self.edit_model.get('axis_xyz', '0, 0, 1'),
            )
        else:
            self.edit_model[target_key] = f"{_fmt_coord(x)}, {_fmt_coord(y)}, {_fmt_coord(z)}"
        if target_key == 'center_xyz':
            edge_text = str(self.edit_model.get('edge_xyz') or '').strip()
            if edge_text:
                ex, ey, ez = _xyz_to_tuple(edge_text)
                self.edit_model['edge_xyz'] = (
                    f"{_fmt_coord(ex + (delta if nudge_axis == 'x' else 0))}, "
                    f"{_fmt_coord(ey + (delta if nudge_axis == 'y' else 0))}, "
                    f"{_fmt_coord(ez + (delta if nudge_axis == 'z' else 0))}"
                )
        self.load_adjust_edits_from_model()
        self.update_measured_value_box()
        self.commit_edit(sync_adjust_edits=False)


__all__ = ["DiameterEditorCoordinator"]
