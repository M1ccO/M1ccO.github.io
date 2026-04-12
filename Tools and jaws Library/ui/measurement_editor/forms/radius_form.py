"""Radius measurement form builder for the measurement editor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLineEdit, QPushButton, QWidget

from .shared_sections import build_xyz_header_row


@dataclass
class RadiusFormRefs:
    """Widget references created by :func:`build_radius_form`."""
    name_edit: QLineEdit
    part_edit: QLineEdit
    center_x_edit: QLineEdit
    center_y_edit: QLineEdit
    center_z_edit: QLineEdit
    center_pick_btn: QPushButton
    axis_x_edit: QLineEdit
    axis_y_edit: QLineEdit
    axis_z_edit: QLineEdit
    value_edit: QLineEdit


def build_radius_form(
    translate: Callable[[str, str | None], str],
    on_schedule_commit: Callable,
    on_pick_center: Callable,
) -> tuple[QWidget, RadiusFormRefs]:
    """Build the radius measurement edit form.

    Returns ``(container_widget, refs)`` where *refs* holds every named widget
    that the dialog needs to read or update.
    """
    container = QWidget()
    form = QFormLayout(container)
    form.setContentsMargins(4, 4, 4, 4)
    form.setSpacing(6)
    form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

    name_edit = QLineEdit()
    name_edit.setPlaceholderText('Radius 1')
    name_edit.editingFinished.connect(on_schedule_commit)
    form.addRow(translate('common.name', 'Name') + ':', name_edit)

    part_edit = QLineEdit()
    part_edit.setPlaceholderText(
        translate('tool_editor.measurements.part_placeholder', '(part name, blank = assembly)'))
    part_edit.editingFinished.connect(on_schedule_commit)
    form.addRow(translate('tool_editor.measurements.part', 'Part') + ':', part_edit)

    form.addRow('', build_xyz_header_row(translate, with_pick=True))
    center_row = QHBoxLayout()
    center_x_edit = QLineEdit('0')
    center_y_edit = QLineEdit('0')
    center_z_edit = QLineEdit('0')
    for axis_edit in (center_x_edit, center_y_edit, center_z_edit):
        axis_edit.setFixedWidth(56)
        axis_edit.editingFinished.connect(on_schedule_commit)
    center_pick_btn = QPushButton(translate('tool_editor.measurements.pick', 'Pick'))
    center_pick_btn.setFixedWidth(50)
    center_pick_btn.clicked.connect(on_pick_center)
    center_row.addWidget(center_x_edit)
    center_row.addWidget(center_y_edit)
    center_row.addWidget(center_z_edit)
    center_row.addStretch(1)
    center_row.addWidget(center_pick_btn)
    form.addRow(translate('tool_editor.measurements.center_xyz', 'Center XYZ') + ':', center_row)

    form.addRow('', build_xyz_header_row(translate, with_pick=False))
    axis_row = QHBoxLayout()
    axis_x_edit = QLineEdit('0')
    axis_y_edit = QLineEdit('1')
    axis_z_edit = QLineEdit('0')
    for axis_edit in (axis_x_edit, axis_y_edit, axis_z_edit):
        axis_edit.setFixedWidth(56)
        axis_edit.editingFinished.connect(on_schedule_commit)
        axis_row.addWidget(axis_edit)
    axis_row.addStretch(1)
    form.addRow(translate('tool_editor.measurements.axis_xyz', 'Axis XYZ') + ':', axis_row)

    value_edit = QLineEdit('10')
    value_edit.editingFinished.connect(on_schedule_commit)
    form.addRow(translate('tool_editor.measurements.radius', 'Radius (mm)') + ':', value_edit)

    return container, RadiusFormRefs(
        name_edit=name_edit,
        part_edit=part_edit,
        center_x_edit=center_x_edit,
        center_y_edit=center_y_edit,
        center_z_edit=center_z_edit,
        center_pick_btn=center_pick_btn,
        axis_x_edit=axis_x_edit,
        axis_y_edit=axis_y_edit,
        axis_z_edit=axis_z_edit,
        value_edit=value_edit,
    )


__all__ = ["RadiusFormRefs", "build_radius_form"]
