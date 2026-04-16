"""Catalog list widgets for HomePage."""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QSize, Qt
from PySide6.QtGui import QDrag, QIcon, QTransform
from PySide6.QtWidgets import QListView

from shared.ui.cards.mini_assignment_card import MiniAssignmentCard
from shared.ui.helpers.dragdrop_helpers import build_text_drag_ghost, build_widget_drag_ghost
try:
    from ..selector_mime import SELECTOR_TOOL_MIME, encode_selector_payload
    from ..tool_catalog_delegate import ROLE_TOOL_DATA, ROLE_TOOL_ID, ROLE_TOOL_UID, tool_icon_for_type
except ImportError:
    from ui.selector_mime import SELECTOR_TOOL_MIME, encode_selector_payload
    from ui.tool_catalog_delegate import ROLE_TOOL_DATA, ROLE_TOOL_ID, ROLE_TOOL_UID, tool_icon_for_type


def _drag_icon_for_payload(tool_type: str, spindle: str) -> QIcon:
    icon = tool_icon_for_type(str(tool_type or '').strip())
    if str(spindle or '').strip().lower() != 'sub' or icon.isNull():
        return icon
    pixmap = icon.pixmap(QSize(22, 22))
    if pixmap.isNull():
        return icon
    return QIcon(pixmap.transformed(QTransform().scale(-1, 1), Qt.SmoothTransformation))


class ToolCatalogListView(QListView):
    """QListView that starts selector-compatible tool drags."""

    def startDrag(self, supportedActions):
        selection_model = self.selectionModel()
        if selection_model is None:
            return
        indexes = sorted(selection_model.selectedRows(), key=lambda idx: idx.row())
        if not indexes:
            current = self.currentIndex()
            if current.isValid():
                indexes = [current]
        if not indexes:
            return

        payload: list[dict] = []
        for index in indexes:
            tool_id = str(index.data(ROLE_TOOL_ID) or '').strip()
            if not tool_id:
                continue
            tool_uid = index.data(ROLE_TOOL_UID)
            tool_data = index.data(ROLE_TOOL_DATA) or {}
            payload.append(
                {
                    'tool_id': tool_id,
                    'id': tool_id,
                    'uid': int(tool_uid or 0),
                    'tool_type': str(tool_data.get('tool_type') if isinstance(tool_data, dict) else '').strip(),
                    'description': str(tool_data.get('description') if isinstance(tool_data, dict) else '').strip(),
                    'default_pot': str(tool_data.get('default_pot') if isinstance(tool_data, dict) else '').strip(),
                    'tool_head': str(tool_data.get('tool_head') if isinstance(tool_data, dict) else '').strip(),
                    'spindle': str(
                        (tool_data.get('spindle_orientation') if isinstance(tool_data, dict) else '')
                        or (tool_data.get('spindle') if isinstance(tool_data, dict) else '')
                    ).strip(),
                }
            )
        if not payload:
            return

        mime = QMimeData()
        encode_selector_payload(mime, SELECTOR_TOOL_MIME, payload)

        drag = QDrag(self)
        drag.setMimeData(mime)

        first = payload[0]
        tool_id = str(first.get('tool_id') or '').strip()
        description = str(first.get('description') or '').strip()
        title = tool_id or 'Tool'
        if description:
            title = f'{title}  -  {description}'
        subtitle = '' if len(payload) <= 1 else f'+{len(payload) - 1} more selected'
        badges: list[str] = []
        default_pot = str(first.get('default_pot') or '').strip()
        if default_pot:
            badges.append(f'P:{default_pot}')

        ghost_card = MiniAssignmentCard(
            icon=_drag_icon_for_payload(first.get('tool_type', ''), first.get('spindle', 'main')),
            title=title,
            subtitle=subtitle,
            badges=badges,
            editable=False,
            compact=True,
            parent=self,
        )
        ghost_card.resize(460, 42 if subtitle else 36)
        ghost_applied = build_widget_drag_ghost(ghost_card, drag)
        ghost_card.deleteLater()

        if not ghost_applied:
            ghost_text = tool_id
            if description:
                ghost_text = f'{ghost_text} - {description}' if ghost_text else description
            if len(payload) > 1:
                ghost_text += f'  (+{len(payload) - 1})'
            build_text_drag_ghost(ghost_text, drag)
        drag.exec(Qt.CopyAction)


__all__ = ['ToolCatalogListView']
