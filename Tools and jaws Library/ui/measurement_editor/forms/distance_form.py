"""Distance measurement form builder for the measurement editor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtGui import QIcon
from PySide6.QtCore import QSize

from .shared_sections import apply_section_groupbox_style, build_adjust_header_row


@dataclass
class DistanceFormRefs:
    """Widget references created by :func:`build_distance_form`."""
    basic_section: QGroupBox
    name_edit: QLineEdit
    pick_points_btn: QPushButton
    pick_status_label: QLabel
    value_mode_btn: QPushButton
    value_edit: QLineEdit
    adjust_section: QGroupBox
    adjust_x_edit: QLineEdit
    adjust_y_edit: QLineEdit
    adjust_z_edit: QLineEdit
    adjust_axis_by_edit: dict
    adjust_active_axis: str
    nudge_step_edit: QLineEdit
    nudge_minus_btn: QPushButton
    nudge_plus_btn: QPushButton
    adjust_mode_btn: QPushButton
    nudge_point_btn: QPushButton


def build_distance_form(
    translate: Callable[[str, str | None], str],
    icon: Callable[[str], QIcon],
    on_schedule_commit: Callable,
    on_pick_target: Callable,
    on_value_mode_toggled: Callable,
    on_point_nudge: Callable[[str], None],
    on_adjust_mode_toggled: Callable,
    on_nudge_point_toggled: Callable,
    event_filter,
) -> tuple[QWidget, DistanceFormRefs]:
    """Build the distance measurement form.

    Returns ``(container_widget, refs)`` where *refs* holds all widget
    references that the dialog unpacks into its own ``self._dist_*`` attributes.
    """
    container = QWidget()
    form = QFormLayout(container)
    form.setContentsMargins(4, 4, 4, 4)
    form.setHorizontalSpacing(6)
    form.setVerticalSpacing(4)
    form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

    basic_section = QGroupBox(translate('tool_editor.measurements.basic_functions', 'Basic functions'))
    apply_section_groupbox_style(basic_section)
    basic_form = QFormLayout(basic_section)
    basic_form.setContentsMargins(8, 6, 8, 6)
    basic_form.setHorizontalSpacing(6)
    basic_form.setVerticalSpacing(3)
    basic_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    basic_section.setMinimumHeight(160)
    basic_section.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    name_edit = QLineEdit()
    name_edit.setPlaceholderText('Distance 1')
    name_edit.editingFinished.connect(on_schedule_commit)
    basic_form.addRow(translate('common.name', 'Name') + ':', name_edit)

    pick_row = QHBoxLayout()
    pick_row.setSpacing(6)
    pick_points_btn = QPushButton('')
    pick_points_btn.setIcon(icon('points_select.svg'))
    pick_points_btn.setIconSize(QSize(24, 24))
    pick_points_btn.setToolTip(translate('tool_editor.measurements.pick', 'Pick'))
    pick_points_btn.setFixedWidth(46)
    pick_points_btn.clicked.connect(on_pick_target)
    pick_status_label = QLabel('')
    pick_status_label.setStyleSheet('color: #6b7b8e; background: transparent;')
    pick_row.addWidget(pick_points_btn)
    pick_row.addWidget(pick_status_label, 1)
    basic_form.addRow(translate('tool_editor.measurements.points', 'Points') + ':', pick_row)

    value_row = QHBoxLayout()
    value_row.setSpacing(6)
    value_mode_btn = QPushButton(translate('tool_editor.measurements.value_mode_measured', 'Measured'))
    value_mode_btn.setCheckable(True)
    value_mode_btn.setChecked(False)  # checked = custom, unchecked = measured
    value_mode_btn.setFixedWidth(100)
    value_mode_btn.clicked.connect(on_value_mode_toggled)
    value_edit = QLineEdit()
    value_edit.setPlaceholderText(
        translate('tool_editor.measurements.value_placeholder', 'Measured or custom value')
    )
    value_edit.editingFinished.connect(on_schedule_commit)
    value_row.addWidget(value_mode_btn)
    value_row.addWidget(value_edit, 1)
    display_lbl = QLabel(translate('tool_editor.measurements.display_value', 'Display\nValue') + ':')
    display_lbl.setAlignment(Qt.AlignRight | Qt.AlignTop)
    display_lbl.setStyleSheet('padding-top: 0px; margin-top: -2px;')
    basic_form.addRow(display_lbl, value_row)
    form.addRow(basic_section)

    adjust_section = QGroupBox('')
    apply_section_groupbox_style(adjust_section)
    adjust_section_layout = QVBoxLayout(adjust_section)
    adjust_section_layout.setContentsMargins(8, 6, 8, 4)
    adjust_section_layout.setSpacing(2)

    adjust_x_edit = QLineEdit('0')
    adjust_y_edit = QLineEdit('0')
    adjust_z_edit = QLineEdit('0')
    adjust_axis_by_edit = {
        adjust_x_edit: 'x',
        adjust_y_edit: 'y',
        adjust_z_edit: 'z',
    }
    adjust_active_axis = 'x'
    nudge_step_edit = QLineEdit('1.0')
    nudge_step_edit.setFixedWidth(74)
    for ae in (adjust_x_edit, adjust_y_edit, adjust_z_edit):
        ae.setFixedWidth(74)
        ae.editingFinished.connect(on_schedule_commit)
        ae.installEventFilter(event_filter)

    precise_top_row = build_adjust_header_row(translate, [
        ('tool_editor.measurements.axis_x', 'X', adjust_x_edit),
        ('tool_editor.measurements.axis_y', 'Y', adjust_y_edit),
        ('tool_editor.measurements.axis_z', 'Z', adjust_z_edit),
        (None, 'mm', nudge_step_edit),
    ])

    nudge_minus_btn = QPushButton('-')
    nudge_minus_btn.setText('\u2212')
    nudge_minus_btn.setFixedSize(34, 34)
    nudge_minus_btn.setStyleSheet('font-size: 19px; font-weight: 700; padding: 0px 0px 2px 0px;')
    nudge_minus_btn.setProperty('arrowMoveButton', True)
    nudge_minus_btn.clicked.connect(lambda: on_point_nudge('-'))
    nudge_minus_btn.setFocusPolicy(Qt.NoFocus)
    nudge_plus_btn = QPushButton('+')
    nudge_plus_btn.setFixedSize(34, 34)
    nudge_plus_btn.setStyleSheet('font-size: 19px; font-weight: 700; padding: 0px 0px 1px 0px;')
    nudge_plus_btn.setProperty('arrowMoveButton', True)
    nudge_plus_btn.clicked.connect(lambda: on_point_nudge('+'))
    nudge_plus_btn.setFocusPolicy(Qt.NoFocus)
    pm_container = QWidget()
    pm_layout = QVBoxLayout(pm_container)
    pm_layout.setContentsMargins(0, 0, 0, 0)
    pm_layout.setSpacing(2)
    pm_layout.addWidget(nudge_plus_btn)
    pm_layout.addWidget(nudge_minus_btn)
    precise_top_row.addSpacing(4)
    precise_top_row.addWidget(pm_container, 0, Qt.AlignBottom)
    precise_top_row.addStretch(1)
    adjust_section_layout.addLayout(precise_top_row)

    adjust_bottom_row = QHBoxLayout()
    adjust_bottom_row.setSpacing(6)
    adjust_bottom_row.setContentsMargins(0, 0, 0, 0)
    adjust_mode_btn = QPushButton('')
    adjust_mode_btn.setCheckable(True)
    adjust_mode_btn.setChecked(False)  # checked = nudge, unchecked = arrow offset
    adjust_mode_btn.setFixedWidth(46)
    adjust_mode_btn.setIconSize(QSize(24, 24))
    adjust_mode_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
    adjust_mode_btn.clicked.connect(on_adjust_mode_toggled)
    adjust_mode_btn.setFocusPolicy(Qt.NoFocus)
    nudge_point_btn = QPushButton('')
    nudge_point_btn.setCheckable(True)
    nudge_point_btn.setChecked(False)  # checked = end, unchecked = start
    nudge_point_btn.setFixedWidth(46)
    nudge_point_btn.setIconSize(QSize(24, 24))
    nudge_point_btn.clicked.connect(on_nudge_point_toggled)
    nudge_point_btn.setVisible(False)
    nudge_point_btn.setFocusPolicy(Qt.NoFocus)
    adjust_bottom_row.addWidget(adjust_mode_btn)
    adjust_bottom_row.addWidget(nudge_point_btn)
    adjust_bottom_row.addStretch(1)
    adjust_section_layout.addLayout(adjust_bottom_row)

    form.addRow(adjust_section)
    adjust_section.setVisible(False)

    refs = DistanceFormRefs(
        basic_section=basic_section,
        name_edit=name_edit,
        pick_points_btn=pick_points_btn,
        pick_status_label=pick_status_label,
        value_mode_btn=value_mode_btn,
        value_edit=value_edit,
        adjust_section=adjust_section,
        adjust_x_edit=adjust_x_edit,
        adjust_y_edit=adjust_y_edit,
        adjust_z_edit=adjust_z_edit,
        adjust_axis_by_edit=adjust_axis_by_edit,
        adjust_active_axis=adjust_active_axis,
        nudge_step_edit=nudge_step_edit,
        nudge_minus_btn=nudge_minus_btn,
        nudge_plus_btn=nudge_plus_btn,
        adjust_mode_btn=adjust_mode_btn,
        nudge_point_btn=nudge_point_btn,
    )
    return container, refs


__all__ = ["DistanceFormRefs", "build_distance_form"]
