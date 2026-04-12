"""Angle measurement form builder for the measurement editor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLineEdit, QPushButton, QWidget

from .shared_sections import build_xyz_header_row


@dataclass
class AngleFormRefs:
    """Widget references created by :func:`build_angle_form`."""
    name_edit: QLineEdit
    part_edit: QLineEdit
    center_x_edit: QLineEdit
    center_y_edit: QLineEdit
    center_z_edit: QLineEdit
    center_pick_btn: QPushButton
    start_x_edit: QLineEdit
    start_y_edit: QLineEdit
    start_z_edit: QLineEdit
    start_pick_btn: QPushButton
    end_x_edit: QLineEdit
    end_y_edit: QLineEdit
    end_z_edit: QLineEdit
    end_pick_btn: QPushButton


def build_angle_form(
    translate: Callable[[str, str | None], str],
    on_schedule_commit: Callable,
    on_pick_center: Callable,
    on_pick_start: Callable,
    on_pick_end: Callable,
) -> tuple[QWidget, AngleFormRefs]:
    """Build the angle measurement edit form.

    Returns ``(container_widget, refs)`` where *refs* holds every named widget
    that the dialog needs to read or update.
    """
    container = QWidget()
    form = QFormLayout(container)
    form.setContentsMargins(4, 4, 4, 4)
    form.setSpacing(6)
    form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

    name_edit = QLineEdit()
    name_edit.setPlaceholderText('Angle 1')
    name_edit.editingFinished.connect(on_schedule_commit)
    form.addRow(translate('common.name', 'Name') + ':', name_edit)

    part_edit = QLineEdit()
    part_edit.setPlaceholderText(
        translate('tool_editor.measurements.part_placeholder', '(part name, blank = assembly)'))
    part_edit.editingFinished.connect(on_schedule_commit)
    form.addRow(translate('tool_editor.measurements.part', 'Part') + ':', part_edit)

    # Center XYZ
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

    # Start XYZ
    form.addRow('', build_xyz_header_row(translate, with_pick=True))
    start_row = QHBoxLayout()
    start_x_edit = QLineEdit('0')
    start_y_edit = QLineEdit('0')
    start_z_edit = QLineEdit('0')
    for axis_edit in (start_x_edit, start_y_edit, start_z_edit):
        axis_edit.setFixedWidth(56)
        axis_edit.editingFinished.connect(on_schedule_commit)
    start_pick_btn = QPushButton(translate('tool_editor.measurements.pick', 'Pick'))
    start_pick_btn.setFixedWidth(50)
    start_pick_btn.clicked.connect(on_pick_start)
    start_row.addWidget(start_x_edit)
    start_row.addWidget(start_y_edit)
    start_row.addWidget(start_z_edit)
    start_row.addStretch(1)
    start_row.addWidget(start_pick_btn)
    form.addRow(translate('tool_editor.measurements.start_xyz', 'Start XYZ') + ':', start_row)

    # End XYZ
    form.addRow('', build_xyz_header_row(translate, with_pick=True))
    end_row = QHBoxLayout()
    end_x_edit = QLineEdit('0')
    end_y_edit = QLineEdit('0')
    end_z_edit = QLineEdit('0')
    for axis_edit in (end_x_edit, end_y_edit, end_z_edit):
        axis_edit.setFixedWidth(56)
        axis_edit.editingFinished.connect(on_schedule_commit)
    end_pick_btn = QPushButton(translate('tool_editor.measurements.pick', 'Pick'))
    end_pick_btn.setFixedWidth(50)
    end_pick_btn.clicked.connect(on_pick_end)
    end_row.addWidget(end_x_edit)
    end_row.addWidget(end_y_edit)
    end_row.addWidget(end_z_edit)
    end_row.addStretch(1)
    end_row.addWidget(end_pick_btn)
    form.addRow(translate('tool_editor.measurements.end_xyz', 'End XYZ') + ':', end_row)

    return container, AngleFormRefs(
        name_edit=name_edit,
        part_edit=part_edit,
        center_x_edit=center_x_edit,
        center_y_edit=center_y_edit,
        center_z_edit=center_z_edit,
        center_pick_btn=center_pick_btn,
        start_x_edit=start_x_edit,
        start_y_edit=start_y_edit,
        start_z_edit=start_z_edit,
        start_pick_btn=start_pick_btn,
        end_x_edit=end_x_edit,
        end_y_edit=end_y_edit,
        end_z_edit=end_z_edit,
        end_pick_btn=end_pick_btn,
    )


__all__ = ["AngleFormRefs", "build_angle_form"]
