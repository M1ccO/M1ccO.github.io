"""Selection and signal handlers for FixturePage."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from shared.ui.helpers.selection_common import (
    connect_selection_model_once,
    on_multi_selection_changed_refresh_label,
    update_selection_count_label as update_multi_selection_count_label,
)
from ui.fixture_catalog_delegate import ROLE_JAW_ID

__all__ = [
    'connect_selection_model',
    'on_current_item_changed',
    'on_item_deleted_internal',
    'on_item_double_clicked',
    'on_item_selected_internal',
    'on_multi_selection_changed',
    'update_selection_count_label',
]


def connect_selection_model(page) -> None:
    """Connect list selection model signals once per model instance."""
    connect_selection_model_once(
        page,
        current_changed_handler=page.on_current_item_changed,
        selection_changed_handler=page._on_multi_selection_changed,
    )


def on_item_selected_internal(page, fixture_id: str, _uid: int) -> None:
    """Handle CatalogPageBase item_selected signal for FixturePage."""
    page.current_jaw_id = str(fixture_id or '').strip() or None
    page._update_selection_count_label()
    if not page._details_hidden:
        page.populate_details(page._get_selected_jaw())
    page._sync_detached_preview(show_errors=False)
    if page.current_jaw_id:
        page.jaw_selected.emit(page.current_jaw_id)


def on_item_deleted_internal(page, fixture_id: str) -> None:
    """Handle CatalogPageBase item_deleted signal for FixturePage."""
    if page.current_jaw_id == fixture_id:
        page.current_jaw_id = None
        page._current_item_id = None
        page.populate_details(None)
    page._sync_detached_preview(show_errors=False)
    page.jaw_deleted.emit(fixture_id)


def on_current_item_changed(page, current, previous) -> None:
    """Track current item and refresh detail panel selection state."""
    _ = previous
    if not current.isValid():
        page.current_jaw_id = None
        page._current_item_id = None
        page._update_selection_count_label()
        page.populate_details(None)
        page._sync_detached_preview(show_errors=False)
        return

    page.current_jaw_id = str(current.data(ROLE_JAW_ID) or '').strip() or None
    page._current_item_id = page.current_jaw_id
    page._update_selection_count_label()
    if not page._details_hidden:
        page.populate_details(page._get_selected_jaw())
    page._sync_detached_preview(show_errors=False)


def on_item_double_clicked(page, index) -> None:
    """Open detail panel or editor on double-click depending on modifiers."""
    if not index.isValid():
        return

    page.current_jaw_id = str(index.data(ROLE_JAW_ID) or '').strip() or None
    page._current_item_id = page.current_jaw_id

    if QApplication.keyboardModifiers() & Qt.ControlModifier:
        page.edit_jaw()
        return

    if page._details_hidden:
        page.show_details()
        QTimer.singleShot(0, lambda: page.populate_details(page._get_selected_jaw()))
        return

    page.hide_details()


def on_multi_selection_changed(page, _selected, _deselected) -> None:
    """Update selected-count label when multi-selection changes."""
    on_multi_selection_changed_refresh_label(page, _selected, _deselected)


def update_selection_count_label(page) -> None:
    """Render selected-count label for multi-selection state."""
    update_multi_selection_count_label(
        page,
        count=len(page._selected_jaw_ids()),
        translation_key='jaw_library.selection.count',
    )
