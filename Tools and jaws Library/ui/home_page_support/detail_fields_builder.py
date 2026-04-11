"""Shared detail-field builders for HomePage detail card rows."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QGridLayout, QLabel, QLineEdit, QSizePolicy, QVBoxLayout, QWidget

from shared.editor_helpers import create_titled_section


def build_detail_field(
    *,
    page,
    label_text: str,
    value_text: str,
    multiline: bool = False,
) -> QWidget:
    """Build a read-only detail field with the same behavior as HomePage."""
    field_group = create_titled_section(label_text)
    field_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
    field_group.setMinimumWidth(0)
    field_group.setProperty("elideGroupTitle", True)
    field_group.setProperty("fullGroupTitle", label_text)
    field_group.installEventFilter(page)
    QTimer.singleShot(0, lambda g=field_group: page._refresh_elided_group_title(g))

    flayout = QVBoxLayout(field_group)
    flayout.setContentsMargins(6, 4, 6, 4)
    flayout.setSpacing(4)

    raw_value = "" if value_text is None else str(value_text)
    if multiline:
        normalized_value = (
            raw_value
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\u2028", "\n")
            .replace("\u2029", "\n")
            .replace("\\n", "\n")
        )
        value_edit = QLabel(normalized_value if normalized_value.strip() else "-")
        value_edit.setWordWrap(True)
        value_edit.setTextInteractionFlags(Qt.TextSelectableByMouse)
        value_edit.setFocusPolicy(Qt.NoFocus)
        value_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        value_edit.setMinimumHeight(32)
        value_edit.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        value_edit.setStyleSheet(
            "QLabel {"
            "  background-color: #ffffff;"
            "  border: 1px solid #c8d4e0;"
            "  border-radius: 6px;"
            "  padding: 6px;"
            "  font-size: 10.5pt;"
            "}"
        )
        value_edit.setToolTip("")
    else:
        value_edit = QLineEdit(raw_value if raw_value.strip() else "-")
        value_edit.setReadOnly(True)
        value_edit.setFocusPolicy(Qt.NoFocus)
        value_edit.setCursorPosition(0)
        value_edit.setToolTip(raw_value.strip() or "-")
        value_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    flayout.addWidget(value_edit)
    return field_group


def add_two_box_row(
    *,
    info: QGridLayout,
    row: int,
    left_label: str,
    left_value: str,
    right_label: str,
    right_value: str,
    build_field,
) -> None:
    info.addWidget(build_field(left_label, left_value), row, 0, 1, 3, Qt.AlignTop)
    info.addWidget(build_field(right_label, right_value), row, 3, 1, 3, Qt.AlignTop)


def add_three_box_row(
    *,
    info: QGridLayout,
    row: int,
    first_label: str,
    first_value: str,
    second_label: str,
    second_value: str,
    third_label: str,
    third_value: str,
    build_field,
) -> None:
    info.addWidget(build_field(first_label, first_value), row, 0, 1, 2, Qt.AlignTop)
    info.addWidget(build_field(second_label, second_value), row, 2, 1, 2, Qt.AlignTop)
    info.addWidget(build_field(third_label, third_value), row, 4, 1, 2, Qt.AlignTop)
