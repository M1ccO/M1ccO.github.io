from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QPushButton, QWidget

try:
    from shared.ui.cards.mini_assignment_card import MiniAssignmentCard
    from shared.ui.helpers.dragdrop_helpers import (
        build_text_drag_ghost,
        build_widget_drag_ghost,
        clear_selection_on_blank_click,
    )
except ModuleNotFoundError:
    _workspace_root = Path(__file__).resolve().parents[3]
    if str(_workspace_root) not in sys.path:
        sys.path.insert(0, str(_workspace_root))
    from shared.ui.cards.mini_assignment_card import MiniAssignmentCard
    from shared.ui.helpers.dragdrop_helpers import (
        build_text_drag_ghost,
        build_widget_drag_ghost,
        clear_selection_on_blank_click,
    )


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
        owner = getattr(self, "_owner", None)
        owner_head = str(getattr(owner, "_head_key", "") or "").strip().upper()
        owner_spindle = ""
        if owner is not None and hasattr(owner, "_current_spindle"):
            try:
                owner_spindle = str(owner._current_spindle() or "").strip().lower()
            except Exception:
                owner_spindle = ""
        for index in indexes:
            item = self.item(index.row())
            if item is None:
                continue
            assignment = item.data(Qt.UserRole)
            if isinstance(assignment, dict):
                enriched = dict(assignment)
                if owner_head and not str(enriched.get("head") or enriched.get("head_key") or "").strip():
                    enriched["head"] = owner_head
                if owner_spindle and not str(enriched.get("spindle") or "").strip():
                    enriched["spindle"] = owner_spindle
                payload.append(enriched)
        _encode_work_editor_tool_payload(mime, payload)

        drag = QDrag(self)
        drag.setMimeData(mime)

        first_row = indexes[0].row()
        ghost_item = self.item(first_row)
        ghost_widget = self.itemWidget(ghost_item) if ghost_item is not None else None
        ghost_applied = False
        if isinstance(ghost_widget, QWidget):
            card_widget = ghost_widget.findChild(MiniAssignmentCard)
            preview_widget = card_widget if isinstance(card_widget, QWidget) else ghost_widget
            ghost_applied = build_widget_drag_ghost(preview_widget, drag)
        if not ghost_applied and payload:
            text = str(payload[0].get("tool_id") or "").strip()
            build_text_drag_ghost(text, drag)

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
        clear_selection_on_blank_click(self, event)
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
