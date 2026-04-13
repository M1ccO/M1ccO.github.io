"""Localization refresh helpers for HomePage.

Extracted from home_page.py (Phase 10 Pass 1).
The single public function apply_home_page_localization() replaces
the large apply_localization() override in home_page.py.
"""

from __future__ import annotations

from typing import Callable

from config import ALL_TOOL_TYPES

__all__ = [
    "apply_home_page_localization",
    "build_tool_type_filter_items",
    "localized_tool_type",
    "tool_id_display_value",
]


def apply_home_page_localization(
    page,
    translate: Callable[[str, str | None], str] | None = None,
) -> None:
    """Refresh all user-visible strings on HomePage after a locale change."""
    if translate is not None:
        page._translate = translate

    current_tool_type = page.type_filter.currentData() if hasattr(page, 'type_filter') else 'All'
    if hasattr(page, 'type_filter'):
        page.type_filter.blockSignals(True)
        page.type_filter.clear()
        build_tool_type_filter_items(page)
        for idx in range(page.type_filter.count()):
            if page.type_filter.itemData(idx) == current_tool_type:
                page.type_filter.setCurrentIndex(idx)
                break
        page.type_filter.blockSignals(False)

    if hasattr(page, 'search_input'):
        page.search_input.setPlaceholderText(
            page._t(
                'tool_library.search.placeholder',
                'Search tool ID, name, dimensions, holder, insert, notes...',
            )
        )
    if hasattr(page, 'toolbar_title_label'):
        page.toolbar_title_label.setText(page.page_title)
    if hasattr(page, 'detail_section_label'):
        page.detail_section_label.setText(
            page._t('tool_library.section.tool_details', 'Tool details')
        )
    if hasattr(page, 'preview_window_btn'):
        page.preview_window_btn.setToolTip(
            page._t('tool_library.preview.toggle', 'Toggle detached 3D preview')
        )
    if hasattr(page, 'edit_btn'):
        page.edit_btn.setText(page._t('tool_library.action.edit_tool', 'EDIT TOOL'))
    if hasattr(page, 'delete_btn'):
        page.delete_btn.setText(page._t('tool_library.action.delete_tool', 'DELETE TOOL'))
    if hasattr(page, 'add_btn'):
        page.add_btn.setText(page._t('tool_library.action.add_tool', 'ADD TOOL'))
    if hasattr(page, 'copy_btn'):
        page.copy_btn.setText(page._t('tool_library.action.copy_tool', 'COPY TOOL'))
    if hasattr(page, 'module_switch_label'):
        page.module_switch_label.setText(page._t('tool_library.module.switch_to', 'Switch to'))

    page._rebuild_filter_row()
    page.refresh_list()


def build_tool_type_filter_items(page) -> None:
    """Populate the tool type filter dropdown with localized entries."""
    page.type_filter.addItem(
        page._t('tool_library.filter.all', 'All'),
        'All',
    )
    for tool_type in ALL_TOOL_TYPES:
        page.type_filter.addItem(
            localized_tool_type(page, tool_type),
            tool_type,
        )


def localized_tool_type(page, tool_type: str) -> str:
    """Return a localized label for the given tool type key."""
    key = str(tool_type or '').strip()
    if not key:
        return '-'
    return page._t(f'tool_library.type.{key.lower().replace(" ", "_")}', key)


def tool_id_display_value(value: str) -> str:
    """Normalize a raw tool ID to display format (e.g. 'T12' from 'T0012')."""
    raw = str(value or '').strip()
    if not raw:
        return ''
    body = raw[1:] if raw.lower().startswith('t') else raw
    digits = ''.join(ch for ch in body if ch.isdigit())
    if digits:
        return f'T{digits}'
    return raw
