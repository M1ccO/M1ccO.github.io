"""Measurement type picker widget builder for the measurement editor."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


def build_measurement_type_picker(
    translate: Callable[[str, str | None], str],
    on_kind_clicked: Callable[[str], None],
) -> QWidget:
    """Build the add-measurement type picker page.

    Returns a container widget with buttons for each measurement kind.
    *on_kind_clicked* is called with the kind string ('length', 'diameter',
    'radius', or 'angle') when the user picks a type.
    """
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(8)

    title = QLabel(translate('tool_editor.measurements.select_type_to_add', 'Select measurement type to add'))
    title.setStyleSheet('color: #5f7082; font-size: 10.5pt; font-weight: 600; background: transparent;')
    layout.addWidget(title)

    top_row = QHBoxLayout()
    top_row.setSpacing(8)
    bottom_row = QHBoxLayout()
    bottom_row.setSpacing(8)

    buttons = [
        (translate('tool_editor.measurements.type_length', 'Length'), 'length', top_row),
        (translate('tool_editor.measurements.type_diameter', 'Diameter'), 'diameter', top_row),
        (translate('tool_editor.measurements.type_radius', 'Radius'), 'radius', bottom_row),
        (translate('tool_editor.measurements.type_angle', 'Angle'), 'angle', bottom_row),
    ]
    for text, kind, row in buttons:
        btn = QPushButton(text)
        btn.setProperty('panelActionButton', True)
        btn.setMinimumHeight(34)
        btn.clicked.connect(lambda _checked=False, k=kind: on_kind_clicked(k))
        row.addWidget(btn, 1)

    layout.addLayout(top_row)
    layout.addLayout(bottom_row)
    layout.addStretch(1)
    return container


__all__ = ["build_measurement_type_picker"]
