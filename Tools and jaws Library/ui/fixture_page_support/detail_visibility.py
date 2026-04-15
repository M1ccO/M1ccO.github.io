"""Detail panel visibility helpers for FixturePage.

Extracted from fixture_page.py (Phase 5 Pass 8).
All functions take the page object as their first argument.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

__all__ = ["hide_jaw_details", "show_jaw_details", "toggle_jaw_details"]


def show_jaw_details(page) -> None:
    """Show the detail panel, or switch selector to details mode."""
    if page._selector_active:
        page._selector_slot_controller.set_selector_panel_mode('details')
        return
    page.setUpdatesEnabled(False)
    page._details_hidden = False
    page.detail_container.show()
    page.detail_header_container.show()
    if not page._last_splitter_sizes:
        total = max(600, page.splitter.width())
        page._last_splitter_sizes = [int(total * 0.62), int(total * 0.38)]
    page.splitter.setSizes(page._last_splitter_sizes)
    page.setUpdatesEnabled(True)
    page.list_view.viewport().update()


def hide_jaw_details(page) -> None:
    """Hide the detail panel, or switch selector to selector mode."""
    if page._selector_active:
        page._selector_slot_controller.set_selector_panel_mode('selector')
        return
    page.setUpdatesEnabled(False)
    page._details_hidden = True
    if page.detail_container.isVisible():
        page._last_splitter_sizes = page.splitter.sizes()
    page.detail_container.hide()
    page.detail_header_container.hide()
    page.splitter.setSizes([1, 0])
    page.setUpdatesEnabled(True)
    page.list_view.viewport().update()


def toggle_jaw_details(page) -> None:
    """Toggle detail panel open/closed; prompt if no fixture is selected."""
    if page._details_hidden:
        fixture = page._get_selected_jaw()
        if fixture is None:
            QMessageBox.information(
                page,
                page._t('jaw_library.message.show_details', 'Show details'),
                page._t('jaw_library.message.select_jaw_first', 'Select a fixture first.'),
            )
            return
        # Show the panel first, then populate on the next tick so the UI
        # does not appear to close/reopen while heavy detail widgets initialize.
        page.show_details()
        QTimer.singleShot(0, lambda: page.populate_details(page._get_selected_jaw()))
        return
    page.hide_details()
