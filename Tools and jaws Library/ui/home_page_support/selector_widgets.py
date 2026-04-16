"""Selector assignment widgets for HomePage tool selector panel."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QPushButton, QWidget

from shared.ui.cards.mini_assignment_card import MiniAssignmentCard
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
        self._set_external_drag_state(False)

    def _set_external_drag_state(self, active: bool) -> None:
        self.setProperty('catalogDragOver', bool(active))
        self.style().unpolish(self)
        self.style().polish(self)
        self.viewport().update()
        self._set_card_drag_state(bool(active))
        frame = self._assignment_frame()
        if frame is not None:
            base_style = frame.property('_baseStyleSheet')
            if not isinstance(base_style, str):
                base_style = frame.styleSheet() or ''
                frame.setProperty('_baseStyleSheet', base_style)
            if active:
                frame.setStyleSheet(
                    base_style
                    + 'QGroupBox { border: 1px solid #00c8ff; }'
                    + 'QGroupBox::title { color: #0f5f8e; }'
                )
            else:
                frame.setStyleSheet(base_style)
            frame.update()

    def _set_card_drag_state(self, active: bool) -> None:
        for row in range(self.count()):
            item = self.item(row)
            host = self.itemWidget(item) if item is not None else None
            if isinstance(host, MiniAssignmentCard):
                card = host
            elif isinstance(host, QWidget):
                card = host.findChild(MiniAssignmentCard)
            else:
                card = None
            if isinstance(card, MiniAssignmentCard):
                card.setProperty('catalogDragOver', bool(active))
                card.style().unpolish(card)
                card.style().polish(card)
                card.update()

    def _assignment_frame(self):
        parent = self.parentWidget()
        while parent is not None:
            if bool(parent.property('selectorAssignmentsFrame')):
                return parent
            parent = parent.parentWidget()
        return None

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
            if event.source() is not self:
                self._set_external_drag_state(True)
            event.acceptProposedAction()
            return
        if event.source() is self:
            self._set_external_drag_state(False)
            super().dragEnterEvent(event)
            return
        self._set_external_drag_state(False)
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_TOOL_MIME):
            if event.source() is not self:
                self._set_external_drag_state(True)
            event.acceptProposedAction()
            return
        if event.source() is self:
            self._set_external_drag_state(False)
            super().dragMoveEvent(event)
            return
        self._set_external_drag_state(False)
        event.ignore()

    def dragLeaveEvent(self, event):
        self._set_external_drag_state(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_TOOL_MIME) and event.source() is not self:
            self._set_external_drag_state(False)
            dropped = decode_tool_payload(event.mimeData())
            point = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            row = self.indexAt(point).row()
            if row < 0:
                row = self.count()
            self.externalToolsDropped.emit(dropped if isinstance(dropped, list) else [], row)
            event.acceptProposedAction()
            return

        self._set_external_drag_state(False)
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
