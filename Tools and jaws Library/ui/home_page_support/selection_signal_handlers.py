"""Selection and signal handlers for HomePage.

Extracted from home_page.py to keep the page class thin and orchestration-focused.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from shared.ui.helpers.selection_common import (
    connect_selection_model_once,
    on_multi_selection_changed_refresh_label,
    update_selection_count_label as update_multi_selection_count_label,
)
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
    page._current_item_id = item_id or None
    page._current_item_uid = int(uid or 0) or None

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
        page._current_item_id = None
        page._current_item_uid = None
        page.populate_details(None)

    preview_btn = getattr(page, 'preview_window_btn', None)
    if preview_btn and preview_btn.isChecked():
        close_detached_preview(page)


def connect_selection_model(page) -> None:
    """Connect list selection model signals once per model instance."""
    connect_selection_model_once(
        page,
        current_changed_handler=page.on_current_item_changed,
        selection_changed_handler=page._on_multi_selection_changed,
    )


def on_multi_selection_changed(page, _selected, _deselected) -> None:
    """Update selected-count label when multi-selection changes."""
    on_multi_selection_changed_refresh_label(page, _selected, _deselected)


def update_selection_count_label(page) -> None:
    """Render selected-count label for multi-selection state."""
    update_multi_selection_count_label(
        page,
        count=len(page._selected_tool_uids()),
        translation_key='tool_library.selection.count',
    )


def on_current_item_changed(page, current, previous) -> None:
    """Track current item and refresh detail panel selection state."""
    _ = previous
    preview_btn = getattr(page, 'preview_window_btn', None)
    if not current.isValid():
        page.current_tool_id = None
        page.current_tool_uid = None
        page._current_item_id = None
        page._current_item_uid = None
        if not page._details_hidden:
            page.populate_details(None)
        if preview_btn and preview_btn.isChecked():
            page._sync_detached_preview(show_errors=False)
        return

    tool_id = str(current.data(ROLE_TOOL_ID) or '').strip()
    uid = current.data(ROLE_TOOL_UID)
    page.current_tool_id = tool_id or None
    page.current_tool_uid = int(uid or 0) or None
    page._current_item_id = page.current_tool_id
    page._current_item_uid = page.current_tool_uid

    if not page._details_hidden:
        page.populate_details(page._get_selected_tool())
    if preview_btn and preview_btn.isChecked():
        page._sync_detached_preview(show_errors=False)


def on_item_double_clicked(page, index) -> None:
    """Open detail panel or editor on double-click depending on modifiers."""
    if not index.isValid():
        return

    page.current_tool_id = str(index.data(ROLE_TOOL_ID) or '').strip() or None
    uid = index.data(ROLE_TOOL_UID)
    page.current_tool_uid = int(uid or 0) or None
    page._current_item_id = page.current_tool_id
    page._current_item_uid = page.current_tool_uid

    if QApplication.keyboardModifiers() & Qt.ControlModifier:
        page.edit_tool()
        return

    if page._details_hidden:
        page.show_details()
        QTimer.singleShot(0, lambda: page.populate_details(page._get_selected_tool()))
        return

    page.hide_details()
