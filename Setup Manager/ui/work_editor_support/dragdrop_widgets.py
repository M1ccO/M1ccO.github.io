from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QPushButton, QWidget

try:
    from shared.ui.cards.mini_assignment_card import MiniAssignmentCard
except ModuleNotFoundError:
    _workspace_root = Path(__file__).resolve().parents[3]
    if str(_workspace_root) not in sys.path:
        sys.path.insert(0, str(_workspace_root))
    from shared.ui.cards.mini_assignment_card import MiniAssignmentCard


WORK_EDITOR_TOOL_ASSIGNMENT_MIME = "application/x-setup-manager-tool-assignment"


def _encode_work_editor_tool_payload(mime: QMimeData, payload: list[dict]) -> None:
    clean_payload = [dict(item) for item in (payload or []) if isinstance(item, dict)]
    mime.setData(WORK_EDITOR_TOOL_ASSIGNMENT_MIME, json.dumps(clean_payload).encode("utf-8"))


def _decode_work_editor_tool_payload(mime: QMimeData) -> list[dict]:
    try:
        raw = bytes(mime.data(WORK_EDITOR_TOOL_ASSIGNMENT_MIME)).decode("utf-8").strip()
    except Exception:
        return []
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    return [dict(item) for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


class WorkEditorToolAssignmentListWidget(QListWidget):
    externalAssignmentsDropped = Signal(list, int, object)
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

        mime = self.model().mimeData(indexes) or QMimeData()
        payload: list[dict] = []
        for index in indexes:
            item = self.item(index.row())
            if item is None:
                continue
            assignment = item.data(Qt.UserRole)
            if isinstance(assignment, dict):
                payload.append(dict(assignment))
        _encode_work_editor_tool_payload(mime, payload)

        drag = QDrag(self)
        drag.setMimeData(mime)

        first_row = indexes[0].row()
        ghost_item = self.item(first_row)
        ghost_widget = self.itemWidget(ghost_item) if ghost_item is not None else None
        if isinstance(ghost_widget, QWidget):
            card_widget = ghost_widget.findChild(MiniAssignmentCard)
            preview_widget = card_widget if isinstance(card_widget, QWidget) else ghost_widget
            grabbed = preview_widget.grab()
            if not grabbed.isNull():
                translucent = QPixmap(grabbed.size())
                translucent.fill(Qt.transparent)
                painter = QPainter(translucent)
                painter.setOpacity(0.7)
                painter.drawPixmap(0, 0, grabbed)
                painter.end()
                drag.setPixmap(translucent)
                drag.setHotSpot(translucent.rect().center())
        elif payload:
            text = str(payload[0].get("tool_id") or "").strip()
            pixmap = QPixmap(220, 40)
            pixmap.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setOpacity(0.75)
            painter.setBrush(QColor("#f0f6fc"))
            painter.setPen(QColor("#637282"))
            painter.drawRoundedRect(1, 1, 218, 38, 6, 6)
            painter.setOpacity(1.0)
            painter.setPen(QColor("#22303c"))
            painter.drawText(10, 4, 200, 32, Qt.AlignVCenter | Qt.TextSingleLine, text)
            painter.end()
            drag.setPixmap(pixmap)
            drag.setHotSpot(pixmap.rect().center())

        drag.exec(Qt.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(WORK_EDITOR_TOOL_ASSIGNMENT_MIME):
            event.acceptProposedAction()
            return
        if event.source() is self:
            super().dragEnterEvent(event)
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(WORK_EDITOR_TOOL_ASSIGNMENT_MIME):
            event.acceptProposedAction()
            return
        if event.source() is self:
            super().dragMoveEvent(event)
            return
        event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasFormat(WORK_EDITOR_TOOL_ASSIGNMENT_MIME) and event.source() is not self:
            dropped = _decode_work_editor_tool_payload(event.mimeData())
            point = event.position().toPoint() if hasattr(event, "position") else event.pos()
            row = self.indexAt(point).row()
            if row < 0:
                row = self.count()
            self.externalAssignmentsDropped.emit(dropped if isinstance(dropped, list) else [], row, event.source())
            event.acceptProposedAction()
            return
        super().dropEvent(event)
        if event.source() is self:
            self.orderChanged.emit()

    def mousePressEvent(self, event):
        point = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if self.itemAt(point) is None:
            self.clearSelection()
            self.setCurrentRow(-1)
        super().mousePressEvent(event)


class WorkEditorToolRemoveDropButton(QPushButton):
    assignmentsDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if _decode_work_editor_tool_payload(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if _decode_work_editor_tool_payload(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event):
        dropped = _decode_work_editor_tool_payload(event.mimeData())
        if not dropped:
            event.ignore()
            return
        self.assignmentsDropped.emit(dropped)
        event.acceptProposedAction()
