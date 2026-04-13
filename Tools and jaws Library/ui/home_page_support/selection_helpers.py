"""Selection state helpers for HomePage.

Extracted from home_page.py (Phase 10 Pass 1).
All functions take the page object as their first argument.
"""

from __future__ import annotations

from ui.tool_catalog_delegate import ROLE_TOOL_UID

__all__ = [
    "get_selected_tool",
    "selected_tool_uids",
    "restore_selection_by_uid",
]


def get_selected_tool(page) -> dict | None:
    """Return currently selected tool dict or None."""
    if not page.current_tool_id:
        return None
    return page.tool_service.get_tool(page.current_tool_id)


def selected_tool_uids(page) -> list[int]:
    """Return list of UIDs for all currently selected tools."""
    if not page.list_view.selectionModel():
        return []
    uids = []
    for idx in page.list_view.selectionModel().selectedIndexes():
        uid = idx.data(ROLE_TOOL_UID)
        if uid:
            uids.append(uid)
    return uids


def restore_selection_by_uid(page, uid: int) -> None:
    """Find and re-select a tool by UID after list refresh."""
    if not page._item_model:
        return
    from ui.tool_catalog_delegate import ROLE_TOOL_UID as _UID
    for row in range(page._item_model.rowCount()):
        idx = page._item_model.index(row, 0)
        if idx.data(_UID) == uid:
            page.list_view.setCurrentIndex(idx)
            page.list_view.scrollTo(idx)
            break
