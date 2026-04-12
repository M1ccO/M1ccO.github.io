from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QTransform

from config import (
    DEFAULT_TOOL_ICON,
    ICONS_DIR,
    TOOL_ICONS_DIR,
    TOOL_LIBRARY_TOOL_ICONS_DIR,
    TOOL_TYPE_TO_ICON,
)


def toolbar_icon(name: str) -> QIcon:
    base = Path(ICONS_DIR) / "tools"
    png = base / f"{name}.png"
    if png.exists():
        return QIcon(str(png))
    svg = base / f"{name}.svg"
    if svg.exists():
        return QIcon(str(svg))
    return QIcon()


def tool_icon_for_type(tool_type: str) -> QIcon:
    icon_name = TOOL_TYPE_TO_ICON.get((tool_type or "").strip(), DEFAULT_TOOL_ICON)
    candidates = [
        Path(TOOL_ICONS_DIR) / icon_name,
        Path(TOOL_LIBRARY_TOOL_ICONS_DIR) / icon_name,
        Path(ICONS_DIR) / "tools" / icon_name,
        Path(TOOL_ICONS_DIR) / DEFAULT_TOOL_ICON,
        Path(TOOL_LIBRARY_TOOL_ICONS_DIR) / DEFAULT_TOOL_ICON,
        Path(ICONS_DIR) / "tools" / DEFAULT_TOOL_ICON,
    ]
    for candidate in candidates:
        if candidate.exists():
            return QIcon(str(candidate))
    return QIcon()


_TURNING_TOOL_TYPES = {
    "O.D Turning",
    "I.D Turning",
    "O.D Groove",
    "I.D Groove",
    "Face Groove",
    "O.D Thread",
    "I.D Thread",
    "Turn Thread",
    "Turn Drill",
    "Turn Spot Drill",
}


def is_turning_tool_type(tool_type: str) -> bool:
    return (tool_type or "").strip() in _TURNING_TOOL_TYPES


def tool_icon_for_type_in_spindle(tool_type: str, spindle: str) -> QIcon:
    icon = tool_icon_for_type(tool_type)
    if icon.isNull():
        return icon
    is_sub = (spindle or "").strip().lower() == "sub"
    if not is_sub or not is_turning_tool_type(tool_type):
        return icon
    pixmap = icon.pixmap(QSize(32, 32))
    if pixmap.isNull():
        return icon
    mirrored = pixmap.transformed(QTransform().scale(-1, 1), Qt.SmoothTransformation)
    return QIcon(mirrored)
