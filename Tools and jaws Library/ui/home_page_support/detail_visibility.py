"""Detail panel visibility helpers for HomePage.

Extracted from home_page.py (Phase 10 Pass 1).
All functions take the page object as their first argument.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from ui.selector_state_helpers import default_selector_splitter_sizes

__all__ = ["hide_tool_details", "show_tool_details", "toggle_tool_details"]


def show_tool_details(page) -> None:
    """Show the detail panel."""
    if not hasattr(page, 'splitter'):
        return
    if not page._details_hidden:
        return
    page.setUpdatesEnabled(False)
    page._details_hidden = False
    if not page._last_splitter_sizes:
        page._last_splitter_sizes = default_selector_splitter_sizes(
            page.splitter.width()
        )
    page.splitter.setSizes(page._last_splitter_sizes)
    page.detail_container.show()
    page.detail_header_container.show()
    page.setUpdatesEnabled(True)
    if hasattr(page, 'tool_list'):
        page.tool_list.viewport().update()


def hide_tool_details(page) -> None:
    """Hide the detail panel."""
    if not hasattr(page, 'splitter'):
        return
    if page._details_hidden:
        return
    page.setUpdatesEnabled(False)
    page._details_hidden = True
    page._last_splitter_sizes = page.splitter.sizes()
    page.splitter.setSizes([1, 0])
    page.detail_container.hide()
    page.detail_header_container.hide()
    page.setUpdatesEnabled(True)
    if hasattr(page, 'tool_list'):
        page.tool_list.viewport().update()


def toggle_tool_details(page) -> None:
    """Toggle detail panel open/closed; prompt if no tool is selected."""
    if page._details_hidden:
        if not page.current_tool_id:
            QMessageBox.information(
                page,
                page._t('tool_library.message.show_details', 'Show details'),
                page._t('tool_library.message.select_tool_first', 'Select a tool first.'),
            )
            return
        # Show the panel first, then populate on the next tick so the UI
        # does not appear to close/reopen while heavy detail widgets initialize.
        page.show_details()
        QTimer.singleShot(0, lambda: page.populate_details(page._get_selected_tool()))
    else:
        page.hide_details()
