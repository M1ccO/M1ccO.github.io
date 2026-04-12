"""Drag-and-drop enabled list widgets and selector row cards for the tool catalog."""

from __future__ import annotations

from PySide6.QtCore import Qt, QMimeData, Signal
from PySide6.QtGui import QDrag, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListView,
    QListWidget,
    QPushButton,
    QWidget,
)

from shared.ui.cards.mini_assignment_card import MiniAssignmentCard
from shared.ui.helpers.dragdrop_helpers import (
    build_text_drag_ghost,
    build_widget_drag_ghost,
    clear_selection_on_blank_click,
)
from ui.selector_mime import (
    SELECTOR_TOOL_MIME,
    decode_tool_payload,
    encode_selector_payload,
    tool_payload_keys,
)
from ui.tool_catalog_delegate import ROLE_TOOL_DATA, ROLE_TOOL_ID, ROLE_TOOL_UID


class ToolCatalogListView(QListView):
    def startDrag(self, supportedActions):
        selection_model = self.selectionModel()
        if selection_model is None:
            return
        indexes = sorted(selection_model.selectedRows(), key=lambda idx: idx.row())
        if not indexes:
            index = self.currentIndex()
            if index.isValid():
                indexes = [index]
        if not indexes:
            return

        payload: list[dict] = []
        for index in indexes:
            tool_id = str(index.data(ROLE_TOOL_ID) or '').strip()
            if not tool_id:
                continue
            entry: dict = {'tool_id': tool_id}
            tool_uid = index.data(ROLE_TOOL_UID)
            try:
                parsed_uid = int(tool_uid) if tool_uid is not None and str(tool_uid).strip() else None
            except Exception:
                parsed_uid = None
            if parsed_uid is not None:
                entry['tool_uid'] = parsed_uid
            tool_data = index.data(ROLE_TOOL_DATA)
            if isinstance(tool_data, dict):
                entry['description'] = str(tool_data.get('description') or '').strip()
                entry['tool_type'] = str(tool_data.get('tool_type') or '').strip()
                entry['default_pot'] = str(tool_data.get('default_pot') or '').strip()
            payload.append(entry)

        if not payload:
            return

        mime = QMimeData()
        encode_selector_payload(mime, SELECTOR_TOOL_MIME, payload)
        drag = QDrag(self)
        drag.setMimeData(mime)

        # Build a semi-transparent ghost card showing the first tool
        first = payload[0]
        ghost_text = first.get('tool_id', '')
        desc = first.get('description', '')
        if desc:
            ghost_text = f'{ghost_text} - {desc}'
        if len(payload) > 1:
            ghost_text += f'  (+{len(payload) - 1})'
        build_text_drag_ghost(ghost_text, drag)

        drag.exec(Qt.CopyAction)


class ToolAssignmentListWidget(QListWidget):
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

        mime = self.model().mimeData(indexes)
        if mime is None:
            mime = QMimeData()

        payload: list[dict] = []
        for index in indexes:
            item = self.item(index.row())
            if item is None:
                continue
            assignment = item.data(Qt.UserRole)
            if isinstance(assignment, dict):
                payload.append(dict(assignment))
        encode_selector_payload(mime, SELECTOR_TOOL_MIME, payload)

        drag = QDrag(self)
        drag.setMimeData(mime)

        first_row = indexes[0].row()
        ghost_item = self.item(first_row)
        ghost_widget = self.itemWidget(ghost_item) if ghost_item is not None else None
        if isinstance(ghost_widget, QWidget):
            card_widget = ghost_widget.findChild(MiniAssignmentCard)
            preview_widget = card_widget if isinstance(card_widget, QWidget) else ghost_widget
            build_widget_drag_ghost(preview_widget, drag)

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


class SelectorToolRemoveDropButton(QPushButton):
    toolsDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    @staticmethod
    def _payload_tool_keys(mime: QMimeData) -> list[tuple[str, str | None]]:
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
        tool_keys = self._payload_tool_keys(event.mimeData())
        if not tool_keys:
            event.ignore()
            return
        self.toolsDropped.emit(tool_keys)
        event.acceptProposedAction()


class SelectorAssignmentRowWidget(MiniAssignmentCard):
    def __init__(
        self,
        icon: QIcon,
        text: str,
        subtitle: str = '',
        comment: str = '',
        pot: str = '',
        parent=None,
    ):
        badges: list[str] = []
        if pot:
            badges.append(f'P:{pot}')
        if comment:
            badges.append('C')
        super().__init__(
            icon=icon,
            title=text,
            subtitle=subtitle,
            badges=badges,
            editable=True,
            compact=True,
            parent=parent,
        )
        self.setObjectName('selectorAssignmentRowCard')
        self._apply_visual_style(False)

    def _apply_visual_style(self, selected: bool) -> None:
        background = '#ffffff'
        border = '#00C8FF' if selected else '#99acbf'
        border_width = '2px' if selected else '1px'
        padding = '0px' if selected else '1px'
        title_color = '#24303c' if selected else '#171a1d'
        meta_color = '#2b3136'
        hint_color = '#617180'
        self.setStyleSheet(
            'QFrame#selectorAssignmentRowCard {'
            f'  background-color: {background};'
            f'  border: {border_width} solid {border};'
            '  border-radius: 8px;'
            f'  padding: {padding};'
            '}'
            'QFrame#selectorAssignmentRowCard QLabel {'
            '  background-color: transparent;'
            '  border: none;'
            '}'
            'QFrame#selectorAssignmentRowCard QLabel[miniAssignmentTitle="true"] {'
            f'  color: {title_color};'
            '}'
            'QFrame#selectorAssignmentRowCard QLabel[miniAssignmentMeta="true"] {'
            f'  color: {meta_color};'
            '}'
            'QFrame#selectorAssignmentRowCard QLabel[miniAssignmentHint="true"] {'
            f'  color: {hint_color};'
            '}'
        )

    def set_selected(self, selected: bool):
        super().set_selected(selected)
        self._apply_visual_style(bool(selected))
