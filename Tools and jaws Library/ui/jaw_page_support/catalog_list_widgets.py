"""Catalog list widgets for JawPage."""

from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QAbstractItemView, QListView

from shared.ui.helpers.dragdrop_helpers import build_text_drag_ghost
try:
    from ..jaw_catalog_delegate import ROLE_JAW_DATA, ROLE_JAW_ID
    from ..selector_mime import SELECTOR_JAW_MIME, encode_selector_payload
except ImportError:
    from ui.jaw_catalog_delegate import ROLE_JAW_DATA, ROLE_JAW_ID
    from ui.selector_mime import SELECTOR_JAW_MIME, encode_selector_payload


class JawCatalogListView(QListView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

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
            jaw_id = str(index.data(ROLE_JAW_ID) or '').strip()
            if not jaw_id:
                continue
            jaw_data = index.data(ROLE_JAW_DATA) or {}
            payload.append(
                {
                    'jaw_id': jaw_id,
                    'jaw_type': str(jaw_data.get('jaw_type') if isinstance(jaw_data, dict) else '').strip(),
                    'spindle_side': str(jaw_data.get('spindle_side') if isinstance(jaw_data, dict) else '').strip(),
                }
            )
        if not payload:
            return

        mime = QMimeData()
        encode_selector_payload(mime, SELECTOR_JAW_MIME, payload)

        drag = QDrag(self)
        drag.setMimeData(mime)

        first = payload[0]
        ghost_text = first.get('jaw_id', '')
        jaw_type = first.get('jaw_type', '')
        if jaw_type:
            ghost_text = f'{ghost_text} - {jaw_type}'
        if len(payload) > 1:
            ghost_text += f'  (+{len(payload) - 1})'
        build_text_drag_ghost(ghost_text, drag)
        drag.exec(Qt.CopyAction)


__all__ = ['JawCatalogListView']