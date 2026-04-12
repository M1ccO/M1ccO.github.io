"""Shared UI section helpers for measurement editor forms."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

SECTION_GROUPBOX_STYLESHEET = (
    "QGroupBox {"
    "  background-color: #f0f6fc;"
    "  border: 1px solid #d0d8e0;"
    "  border-radius: 6px;"
    "  margin-top: 10px;"
    "  padding-top: 8px;"
    "}"
    "QGroupBox::title {"
    "  subcontrol-origin: margin;"
    "  left: 10px;"
    "  padding: 0 4px;"
    "  color: #5a6b7c;"
    "  font-size: 8pt;"
    "  font-weight: 600;"
    "}"
)

ADJUST_HEADER_LABEL_STYLE = (
    "color: #6b7b8e; font-size: 9pt; background: transparent; "
    "padding: 0px 0px 1px 0px;"
)


def apply_section_groupbox_style(groupbox: QGroupBox) -> None:
    groupbox.setStyleSheet(SECTION_GROUPBOX_STYLESHEET)


def build_adjust_header_row(
    translate: Callable[[str, str | None], str],
    columns: Iterable[tuple[str | None, str, QLineEdit]],
    on_header_created: Callable[[QLabel, str | None], None] | None = None,
) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(4)
    row.setContentsMargins(0, 0, 0, 0)

    for header_key, header_fallback, edit in columns:
        col = QVBoxLayout()
        col.setSpacing(1)
        col.setContentsMargins(0, 0, 0, 0)

        header_text = translate(header_key, header_fallback) if header_key else header_fallback
        header_label = QLabel(header_text)
        header_label.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        header_label.setStyleSheet(ADJUST_HEADER_LABEL_STYLE)
        if on_header_created is not None:
            on_header_created(header_label, header_key)

        col.addWidget(header_label)
        col.addWidget(edit)
        row.addLayout(col)

    return row


def build_xyz_header_row(
    translate: Callable[[str, str | None], str],
    with_pick: bool,
    axis_order: list | None = None,
) -> QWidget:
    """Build a row of axis header labels (X / Y / Z) above coordinate edits."""
    if axis_order is None:
        axis_order = ['x', 'y', 'z']

    row_widget = QWidget()
    row_layout = QHBoxLayout(row_widget)
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.setSpacing(6)

    for axis in axis_order:
        key = f'tool_editor.measurements.axis_{axis}'
        fallback = axis.upper()
        lbl = QLabel(translate(key, fallback))
        lbl.setFixedWidth(56)
        lbl.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        lbl.setStyleSheet('color: #6b7b8e; font-size: 10px; background: transparent;')
        row_layout.addWidget(lbl)

    row_layout.addStretch(1)
    if with_pick:
        row_layout.addSpacing(50)
    return row_widget


__all__ = [
    "apply_section_groupbox_style",
    "build_adjust_header_row",
    "build_xyz_header_row",
]
