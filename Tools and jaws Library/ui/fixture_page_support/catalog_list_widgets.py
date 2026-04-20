"""Catalog list widgets for FixturePage."""

from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QAbstractItemView, QListView

from shared.ui.helpers.dragdrop_helpers import build_text_drag_ghost
from ui.fixture_catalog_delegate import ROLE_FIXTURE_DATA, ROLE_FIXTURE_ID
from ui.selector_mime import SELECTOR_FIXTURE_MIME, encode_selector_payload


class FixtureCatalogListView(QListView):
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
            fixture_id = str(index.data(ROLE_FIXTURE_ID) or '').strip()
            if not fixture_id:
                continue
            fixture_data = index.data(ROLE_FIXTURE_DATA) or {}
            payload.append(
                {
                    'fixture_id': fixture_id,
                    'fixture_type': str(fixture_data.get('fixture_type') if isinstance(fixture_data, dict) else '').strip(),
                    'fixture_kind': str(fixture_data.get('fixture_kind') if isinstance(fixture_data, dict) else '').strip(),
                }
            )
        if not payload:
            return

        mime = QMimeData()
        encode_selector_payload(mime, SELECTOR_FIXTURE_MIME, payload)

        drag = QDrag(self)
        drag.setMimeData(mime)

        first = payload[0]
        ghost_text = first.get('fixture_id', '')
        fixture_type = first.get('fixture_type', '')
        if fixture_type:
            ghost_text = f'{ghost_text} - {fixture_type}'
        if len(payload) > 1:
            ghost_text += f'  (+{len(payload) - 1})'
        build_text_drag_ghost(ghost_text, drag)
        drag.exec(Qt.CopyAction)


__all__ = ['FixtureCatalogListView']

