"""Shared drag-and-drop primitive helpers.

These utilities encapsulate the ghost-pixmap rendering and blank-click
deselection patterns that appear in both the Setup Manager and the Tools
and Jaws Library drag-drop widgets.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QDrag, QPainter, QPixmap
from PySide6.QtWidgets import QWidget


def build_text_drag_ghost(text: str, drag: QDrag) -> None:
    """Render a text-label ghost pixmap and attach it to *drag*.

    Draws a rounded-rectangle chip with *text* using the standard
    assignment-card colour palette.
    """
    pixmap = QPixmap(220, 40)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setOpacity(0.75)
    painter.setBrush(QColor('#f0f6fc'))
    painter.setPen(QColor('#637282'))
    painter.drawRoundedRect(1, 1, 218, 38, 6, 6)
    painter.setOpacity(1.0)
    painter.setPen(QColor('#22303c'))
    painter.drawText(10, 4, 200, 32, Qt.AlignVCenter | Qt.TextSingleLine, text)
    painter.end()
    drag.setPixmap(pixmap)
    drag.setHotSpot(pixmap.rect().center())


def build_widget_drag_ghost(widget: QWidget, drag: QDrag) -> bool:
    """Grab *widget* and attach a semi-transparent ghost to *drag*.

    Returns ``True`` when a non-null grab was produced and applied.
    """
    grabbed = widget.grab()
    if grabbed.isNull():
        return False
    translucent = QPixmap(grabbed.size())
    translucent.fill(Qt.transparent)
    painter = QPainter(translucent)
    painter.setOpacity(0.7)
    painter.drawPixmap(0, 0, grabbed)
    painter.end()
    drag.setPixmap(translucent)
    drag.setHotSpot(translucent.rect().center())
    return True


def clear_selection_on_blank_click(list_widget, event) -> None:
    """Clear list selection when the user clicks on an empty area.

    Call at the top of a ``QListWidget.mousePressEvent`` override before
    forwarding the event to ``super()``.
    """
    point = event.position().toPoint() if hasattr(event, 'position') else event.pos()
    if list_widget.itemAt(point) is None:
        list_widget.clearSelection()
        list_widget.setCurrentRow(-1)


__all__ = [
    "build_text_drag_ghost",
    "build_widget_drag_ghost",
    "clear_selection_on_blank_click",
]
