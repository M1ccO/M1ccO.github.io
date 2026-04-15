"""Selection state helpers for FixturePage.

Extracted from fixture_page.py (Phase 5 Pass 8).
All functions take the page object as their first argument.
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex

from ui.fixture_catalog_delegate import ROLE_FIXTURE_DATA

__all__ = [
    "clear_fixture_selection",
    "selected_fixture_ids",
    "selected_fixtures_for_setup_assignment",
]


def clear_fixture_selection(page) -> None:
    """Clear list selection and hide details when appropriate."""
    details_were_open = not page._details_hidden
    model = page.fixture_list.selectionModel()
    if model is not None:
        model.clearSelection()
        page.fixture_list.setCurrentIndex(QModelIndex())
    page.current_fixture_id = None
    page._current_item_id = None
    page._current_item_uid = None
    page._update_selection_count_label()
    page.populate_details(None)
    page._sync_detached_preview(show_errors=False)
    if details_were_open and not page._selector_active:
        page.hide_details()


def selected_fixture_ids(page) -> list[str]:
    """Return the fixture_id of every selected list item, in row order."""
    selection_model = page.fixture_list.selectionModel()
    if selection_model is None:
        return []
    fixture_ids: list[str] = []
    for index in sorted(selection_model.selectedIndexes(), key=lambda idx: idx.row()):
        fixture_id = page._catalog_item_id(index)
        if fixture_id and fixture_id not in fixture_ids:
            fixture_ids.append(fixture_id)
    return fixture_ids


def selected_fixtures_for_setup_assignment(page) -> list[dict]:
    """Return fixture dicts (fixture_id + fixture_type) for all selected items."""
    selection_model = page.fixture_list.selectionModel()
    if selection_model is None:
        return []
    payload: list[dict] = []
    for index in sorted(selection_model.selectedIndexes(), key=lambda idx: idx.row()):
        fixture_id = page._catalog_item_id(index)
        fixture_data = index.data(ROLE_FIXTURE_DATA) or {}
        payload.append({'fixture_id': fixture_id, 'fixture_type': str(fixture_data.get('fixture_type') or '').strip()})
    return payload


