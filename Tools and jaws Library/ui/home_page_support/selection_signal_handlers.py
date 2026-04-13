"""Selection and signal handlers for HomePage.

Extracted from home_page.py to keep the page class thin and orchestration-focused.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui.home_page_support.detached_preview import close_detached_preview
from ui.tool_catalog_delegate import ROLE_TOOL_ID, ROLE_TOOL_UID

__all__ = [
    "connect_selection_model",
    "on_current_item_changed",
    "on_item_deleted_internal",
    "on_item_double_clicked",
    "on_item_selected_internal",
    "on_multi_selection_changed",
    "update_selection_count_label",
]


def on_item_selected_internal(page, item_id: str, uid: int) -> None:
    """Handle CatalogPageBase item_selected signal for HomePage."""
    page.current_tool_id = item_id
    page.current_tool_uid = uid

    if not page._details_hidden:
        tool = page.tool_service.get_tool_by_uid(uid) if uid else None
        if tool is None and item_id:
            tool = page.tool_service.get_tool(item_id)
        page.populate_details(tool)

    preview_btn = getattr(page, 'preview_window_btn', None)
    if preview_btn and preview_btn.isChecked():
        page._sync_detached_preview(show_errors=False)


def on_item_deleted_internal(page, item_id: str) -> None:
    """Handle CatalogPageBase item_deleted signal for HomePage."""
    if page.current_tool_id == item_id:
        page.current_tool_id = None
        page.current_tool_uid = None
        page.populate_details(None)

    preview_btn = getattr(page, 'preview_window_btn', None)
    if preview_btn and preview_btn.isChecked():
        close_detached_preview(page)


def connect_selection_model(page) -> None:
    """Connect list selection model signals once per model instance."""
    selection_model = page.list_view.selectionModel()
    if (
        selection_model is None
        or getattr(page, '_selection_model_connected', None) is selection_model
    ):
        return
    selection_model.currentChanged.connect(page.on_current_item_changed)
    selection_model.selectionChanged.connect(page._on_multi_selection_changed)
    page._selection_model_connected = selection_model


def on_multi_selection_changed(page, _selected, _deselected) -> None:
    """Update selected-count label when multi-selection changes."""
    page._update_selection_count_label()


def update_selection_count_label(page) -> None:
    """Render selected-count label for multi-selection state."""
    count = len(page._selected_tool_uids())
    if count > 1 and hasattr(page, 'selection_count_label'):
        page.selection_count_label.setText(
            page._t('tool_library.selection.count', '{count} selected', count=count)
        )
        page.selection_count_label.show()
        return
    if hasattr(page, 'selection_count_label'):
        page.selection_count_label.hide()


def on_current_item_changed(page, current, previous) -> None:
    """Track current item and refresh detail panel selection state."""
    _ = previous
    if not current.isValid():
        page.current_tool_id = None
        page.current_tool_uid = None
        return

    tool_id = str(current.data(ROLE_TOOL_ID) or '').strip()
    uid = current.data(ROLE_TOOL_UID)
    page.current_tool_id = tool_id or None
    page.current_tool_uid = int(uid or 0) or None

    if not page._details_hidden:
        page.populate_details(page._get_selected_tool())


def on_item_double_clicked(page, index) -> None:
    """Open detail panel or editor on double-click depending on modifiers."""
    if not index.isValid():
        return

    page.current_tool_id = str(index.data(ROLE_TOOL_ID) or '').strip() or None
    uid = index.data(ROLE_TOOL_UID)
    page.current_tool_uid = int(uid or 0) or None

    if QApplication.keyboardModifiers() & Qt.ControlModifier:
        page.edit_tool()
        return

    if page._details_hidden:
        page.populate_details(page._get_selected_tool())
        page.show_details()
        return

    page.hide_details()
