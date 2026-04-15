"""Selector assignment widgets for HomePage tool selector panel."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QPushButton

from shared.ui.helpers.dragdrop_helpers import (
    build_text_drag_ghost,
    build_widget_drag_ghost,
    clear_selection_on_blank_click,
)
from ui.selector_mime import SELECTOR_TOOL_MIME, decode_tool_payload, encode_selector_payload, tool_payload_keys


class ToolAssignmentListWidget(QListWidget):
    """Drop target + reorderable list for selector-assigned tools."""

    externalToolsDropped = Signal(list, int)
    orderChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)

    def startDrag(self, supportedActions):
        indexes = sorted(self.selectedIndexes(), key=lambda idx: idx.row())
        if not indexes:
            current = self.currentIndex()
            if current.isValid():
                indexes = [current]
        if not indexes:
            return

        payload: list[dict] = []
        for index in indexes:
            item = self.item(index.row())
            if item is None:
                continue
            assignment = item.data(Qt.UserRole)
            if isinstance(assignment, dict):
                payload.append(dict(assignment))
        if not payload:
            return

        mime = self.model().mimeData(indexes)
        if mime is None:
            from PySide6.QtCore import QMimeData

            mime = QMimeData()
        encode_selector_payload(mime, SELECTOR_TOOL_MIME, payload)

        drag = QDrag(self)
        drag.setMimeData(mime)

        # Mirror jaw/work-editor behavior: show a translucent snapshot of the
        # dragged card so reorder/drop targeting is easier to track visually.
        preview_item = self.item(indexes[0].row())
        preview_widget = self.itemWidget(preview_item) if preview_item is not None else None
        ghost_applied = False
        if preview_widget is not None:
            ghost_applied = build_widget_drag_ghost(preview_widget, drag)
        if not ghost_applied:
            first_payload = payload[0] if payload else {}
            label = str(first_payload.get('tool_id') or first_payload.get('id') or '').strip()
            if not label:
                label = f"{len(payload)} tool(s)"
            build_text_drag_ghost(label, drag)

        drag.exec(Qt.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_TOOL_MIME):
            event.acceptProposedAction()
            return
        if event.source() is self:
            super().dragEnterEvent(event)
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_TOOL_MIME):
            event.acceptProposedAction()
            return
        if event.source() is self:
            super().dragMoveEvent(event)
            return
        event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_TOOL_MIME) and event.source() is not self:
            dropped = decode_tool_payload(event.mimeData())
            point = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            row = self.indexAt(point).row()
            if row < 0:
                row = self.count()
            self.externalToolsDropped.emit(dropped if isinstance(dropped, list) else [], row)
            event.acceptProposedAction()
            return

        super().dropEvent(event)
        if event.source() is self:
            self.orderChanged.emit()

    def mousePressEvent(self, event):
        clear_selection_on_blank_click(self, event)
        super().mousePressEvent(event)


class ToolSelectorRemoveDropButton(QPushButton):
    """Remove button that accepts dropped selector tools."""

    toolsDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    @staticmethod
    def _payload_tool_keys(mime) -> list[tuple[str, str | None]]:
        return tool_payload_keys(mime)

    def dragEnterEvent(self, event):
        if self._payload_tool_keys(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if self._payload_tool_keys(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event):
        dropped = decode_tool_payload(event.mimeData())
        if not dropped:
            event.ignore()
            return
        self.toolsDropped.emit(dropped)
        event.acceptProposedAction()


__all__ = ['ToolAssignmentListWidget', 'ToolSelectorRemoveDropButton']
