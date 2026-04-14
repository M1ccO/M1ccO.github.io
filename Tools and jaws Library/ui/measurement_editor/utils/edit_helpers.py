"""Static helpers for reading and writing QLineEdit XYZ triplets."""

from __future__ import annotations

from PySide6.QtWidgets import QLineEdit

from .coordinates import xyz_to_tuple, fmt_coord


def set_xyz_edits(
    edits: tuple[QLineEdit, QLineEdit, QLineEdit],
    value,
) -> None:
    x, y, z = xyz_to_tuple(value)
    edits[0].setText(fmt_coord(x))
    edits[1].setText(fmt_coord(y))
    edits[2].setText(fmt_coord(z))


def xyz_text_from_edits(edits: tuple[QLineEdit, QLineEdit, QLineEdit]) -> str:
    values = []
    defaults = [0.0, 0.0, 0.0]
    for i, edit in enumerate(edits):
        text = edit.text().strip().replace(',', '.')
        try:
            values.append(float(text))
        except Exception:
            values.append(defaults[i])
    return f"{fmt_coord(values[0])}, {fmt_coord(values[1])}, {fmt_coord(values[2])}"


def focused_axis(edits: tuple[QLineEdit, QLineEdit, QLineEdit]) -> str:
    if edits[0].hasFocus():
        return 'x'
    if edits[1].hasFocus():
        return 'y'
    if edits[2].hasFocus():
        return 'z'
    return 'all'


__all__ = ["set_xyz_edits", "xyz_text_from_edits", "focused_axis"]
