from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget


def normalize_selector_spindle(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    return "sub" if raw in {"sub", "sp2", "2"} else "main"


def selector_spindle_label(spindle: str) -> str:
    return "SP2" if normalize_selector_spindle(spindle) == "sub" else "SP1"


def event_point(event) -> QPoint | None:
    if hasattr(event, "position"):
        pos = event.position()
        try:
            return pos.toPoint()
        except Exception:
            pass
    if hasattr(event, "pos"):
        return event.pos()
    return None


def widget_contains_global_point(widget: QWidget | None, global_pos: QPoint) -> bool:
    if widget is None:
        return False
    local = widget.mapFromGlobal(global_pos)
    return widget.rect().contains(local)
