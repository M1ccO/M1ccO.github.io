from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QBoxLayout, QComboBox, QGridLayout, QGroupBox, QLabel, QLineEdit, QSizePolicy, QVBoxLayout, QWidget


def make_zero_axis_input(dialog: Any, value_attr_name: str, axis: str) -> QLineEdit:
    value_input = QLineEdit()
    value_input.setPlaceholderText(axis.upper())
    value_input.setMinimumWidth(88)
    setattr(dialog, value_attr_name, value_input)
    return value_input


def set_zero_xy_visibility(dialog: Any, show_xy: bool) -> None:
    for axis in ("z", "c"):
        for widget in dialog._zero_axis_widgets.get(axis, []):
            widget.setVisible(True)
    for axis in ("x", "y"):
        for widget in dialog._zero_axis_widgets.get(axis, []):
            widget.setVisible(show_xy)

    for spacer in dialog._zero_row_spacers:
        spacer.setMinimumWidth(56 if show_xy else 0)

    for combo in dialog._zero_coord_combos:
        if show_xy:
            combo.setMinimumWidth(92)
            combo.setMaximumWidth(16777215)
        else:
            combo.setMinimumWidth(74)
            combo.setMaximumWidth(16777215)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    zc_min = 74 if not show_xy else 88
    for axis in ("z", "c"):
        for value_input in dialog._zero_axis_inputs.get(axis, []):
            value_input.setMinimumWidth(zc_min)
            value_input.setMaximumWidth(16777215)
            value_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    axis_columns = {"z": 2, "x": 3, "y": 4, "c": 5}
    axis_stretch = {"z": 1, "x": 1 if show_xy else 0, "y": 1 if show_xy else 0, "c": 1}
    for grid in dialog._zero_point_grids:
        grid.setHorizontalSpacing(6 if show_xy else 2)
        for axis, col in axis_columns.items():
            grid.setColumnStretch(col, axis_stretch[axis])
        grid.setColumnStretch(1, 1 if show_xy else 0)
        grid.setColumnStretch(0, 0)
        grid.setColumnMinimumWidth(0, 72 if show_xy else 58)

    for grid, _group in dialog._zero_grids_with_groups:
        if show_xy:
            grid.setContentsMargins(12, 8, 12, 8)
        else:
            grid.setContentsMargins(8, 6, 8, 6)

    if hasattr(dialog, "zero_points_host"):
        dialog.zero_points_host._switch_width = 1320 if show_xy else 820
        direction = (
            QBoxLayout.TopToBottom
            if dialog.zero_points_host.width() < dialog.zero_points_host._switch_width
            else QBoxLayout.LeftToRight
        )
        if dialog.zero_points_host._layout.direction() != direction:
            dialog.zero_points_host._layout.setDirection(direction)
            dialog.zero_points_host._update_separator_shapes()


def build_spindle_zero_group(
    dialog: Any,
    title: str,
    spindle_key: str,
    *,
    create_titled_section_fn: Callable[[str], object],
    work_coordinates: list[str] | tuple[str, ...],
) -> QGroupBox:
    group = create_titled_section_fn(title)
    group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    root = QVBoxLayout(group)
    root.setContentsMargins(8, 6, 8, 8)
    root.setSpacing(8)

    grid_host = QWidget(group)
    grid = QGridLayout(grid_host)
    grid.setContentsMargins(12, 8, 12, 8)
    grid.setHorizontalSpacing(8)
    grid.setVerticalSpacing(6)
    dialog._zero_point_grids.append(grid)
    dialog._zero_grids_with_groups.append((grid, group))

    spacer = QLabel("")
    spacer.setMinimumWidth(56)
    grid.addWidget(spacer, 0, 0)
    dialog._zero_row_spacers.append(spacer)

    coord_header = QLabel("WCS")
    coord_header.setProperty("detailFieldKey", True)
    coord_header.setAlignment(Qt.AlignCenter)
    grid.addWidget(coord_header, 0, 1)

    for col, axis in enumerate(dialog._zero_axes, start=2):
        axis_header = QLabel(axis.upper())
        axis_header.setProperty("detailFieldKey", True)
        axis_header.setAlignment(Qt.AlignCenter)
        grid.addWidget(axis_header, 0, col)
        dialog._zero_axis_widgets[axis].append(axis_header)

    for row, head in enumerate(dialog.machine_profile.heads, start=1):
        head_key = head.key
        head_prefix = head_key.lower()
        head_label = QLabel(dialog._t(f"setup_page.section.{head_key.lower()}", head_key))
        head_label.setWordWrap(False)
        grid.addWidget(head_label, row, 0)

        combo_attr_name = f"{head_prefix}_{spindle_key}_coord_combo"
        coord_combo = QComboBox()
        coord_combo.addItems(list(work_coordinates))
        coord_combo.setProperty("modernDropdown", True)
        coord_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        coord_combo.setMinimumWidth(92)
        dialog._apply_coord_combo_popup_style(coord_combo)
        dialog._zero_coord_combos.append(coord_combo)
        dialog._zero_coord_inputs[(head_key, spindle_key)] = coord_combo
        setattr(dialog, combo_attr_name, coord_combo)
        grid.addWidget(coord_combo, row, 1)

        for col, axis in enumerate(dialog._zero_axes, start=2):
            value_attr_name = f"{head_prefix}_{spindle_key}_{axis}_input"
            value_input = make_zero_axis_input(dialog, value_attr_name, axis)
            grid.addWidget(value_input, row, col)
            dialog._zero_axis_widgets[axis].append(value_input)
            dialog._zero_axis_inputs[axis].append(value_input)
            dialog._zero_axis_input_map[(head_key, spindle_key, axis)] = value_input

    grid.setColumnStretch(0, 0)
    grid.setColumnStretch(1, 1)
    for col in range(2, 2 + len(dialog._zero_axes)):
        grid.setColumnStretch(col, 1)
    root.addWidget(grid_host, 0)

    return group


def set_coord_combo(combo: QComboBox, value: str, default: str):
    target = (value or "").strip() or default
    index = combo.findText(target)
    combo.setCurrentIndex(index if index >= 0 else combo.findText(default))
