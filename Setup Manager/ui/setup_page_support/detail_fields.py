from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


def make_detail_field(label_text: str, value_text: str) -> QFrame:
    field = QFrame()
    field.setProperty("detailField", True)
    fl = QVBoxLayout(field)
    fl.setContentsMargins(6, 4, 6, 4)
    fl.setSpacing(4)
    key_lbl = QLabel(label_text)
    key_lbl.setProperty("detailFieldKey", True)
    val_lbl = QLabel((value_text or "").strip())
    val_lbl.setProperty("detailFieldValue", True)
    val_lbl.setWordWrap(True)
    val_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    fl.addWidget(key_lbl)
    fl.addWidget(val_lbl)
    return field


def clear_section(detail_sections: dict, key: str) -> None:
    layout = detail_sections[key]
    while layout.count() > 1:
        item = layout.takeAt(1)
        widget = item.widget()
        if widget:
            widget.deleteLater()


def set_section_fields(detail_sections: dict, key: str, fields: list, make_detail_field_fn) -> None:
    """Rebuild a detail section with (label, value) field pairs."""
    layout = detail_sections[key]
    clear_section(detail_sections, key)
    added = 0
    for label_text, value_text in fields:
        vt = (value_text or "").strip()
        if not vt or vt == "-":
            continue
        layout.addWidget(make_detail_field_fn(label_text, vt))
        added += 1
    if added == 0:
        placeholder = QLabel("-")
        placeholder.setProperty("detailHint", True)
        layout.addWidget(placeholder)


def spindle_zero_text(coord, axis_values: dict[str, str]) -> str:
    coord = (coord or "").strip()
    axis_colors = {
        "z": "#1E5AA8",
        "x": "#3A495A",
        "y": "#3A6E45",
        "c": "#C96A12",
    }
    axis_parts: list[str] = []
    for axis in ("z", "x", "y", "c"):
        value = (axis_values.get(axis) or "").strip()
        if value:
            color = axis_colors.get(axis, "#22303c")
            axis_parts.append(
                f"<span style='font-weight:700; color:{color};'>{axis.upper()}</span>{escape(value)}"
            )
    if not axis_parts:
        return ""
    axis_text = " ".join(axis_parts)
    if coord:
        return f"{escape(coord)} | {axis_text}"
    return axis_text


def head_zero_fields(work: dict, prefix: str, main_title: str, sub_title: str) -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = []
    for spindle_key, spindle_title in (("main", main_title), ("sub", sub_title)):
        coord = work.get(f"{prefix}_{spindle_key}_coord") or work.get(f"{prefix}_zero")
        values = {
            axis: work.get(f"{prefix}_{spindle_key}_{axis}")
            for axis in ("z", "x", "y", "c")
        }
        text = spindle_zero_text(coord, values)
        if text:
            fields.append((spindle_title, text))
    return fields
