"""Selection state helpers for JawPage.

Extracted from jaw_page.py (Phase 5 Pass 8).
All functions take the page object as their first argument.
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex

from ui.jaw_catalog_delegate import ROLE_JAW_DATA

__all__ = [
    "clear_jaw_selection",
    "selected_jaw_ids",
    "selected_jaws_for_setup_assignment",
]


def clear_jaw_selection(page) -> None:
    """Clear list selection and hide details when appropriate."""
    details_were_open = not page._details_hidden
    model = page.jaw_list.selectionModel()
    if model is not None:
        model.clearSelection()
        page.jaw_list.setCurrentIndex(QModelIndex())
    page.current_jaw_id = None
    page._current_item_id = None
    page._current_item_uid = None
    page._update_selection_count_label()
    page.populate_details(None)
    page._sync_detached_preview(show_errors=False)
    if details_were_open and not page._selector_active:
        page.hide_details()


def selected_jaw_ids(page) -> list[str]:
    """Return the jaw_id of every selected list item, in row order."""
    selection_model = page.jaw_list.selectionModel()
    if selection_model is None:
        return []
    jaw_ids: list[str] = []
    for index in sorted(selection_model.selectedIndexes(), key=lambda idx: idx.row()):
        jaw_id = page._catalog_item_id(index)
        if jaw_id and jaw_id not in jaw_ids:
            jaw_ids.append(jaw_id)
    return jaw_ids


def selected_jaws_for_setup_assignment(page) -> list[dict]:
    """Return jaw dicts (jaw_id + jaw_type) for all selected items."""
    selection_model = page.jaw_list.selectionModel()
    if selection_model is None:
        return []
    payload: list[dict] = []
    for index in sorted(selection_model.selectedIndexes(), key=lambda idx: idx.row()):
        jaw_id = page._catalog_item_id(index)
        jaw_data = index.data(ROLE_JAW_DATA) or {}
        payload.append({'jaw_id': jaw_id, 'jaw_type': str(jaw_data.get('jaw_type') or '').strip()})
    return payload
