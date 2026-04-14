"""Catalog list widgets for HomePage."""

from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QListView

from shared.ui.helpers.dragdrop_helpers import build_text_drag_ghost
from ui.selector_mime import SELECTOR_TOOL_MIME, encode_selector_payload
from ui.tool_catalog_delegate import ROLE_TOOL_DATA, ROLE_TOOL_ID, ROLE_TOOL_UID


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
        ghost_text = first.get('tool_id', '')
        desc = first.get('description', '')
        if desc:
            ghost_text = f'{ghost_text} - {desc}'
        if len(payload) > 1:
            ghost_text += f'  (+{len(payload) - 1})'
        build_text_drag_ghost(ghost_text, drag)
        drag.exec(Qt.CopyAction)


__all__ = ['ToolCatalogListView']
