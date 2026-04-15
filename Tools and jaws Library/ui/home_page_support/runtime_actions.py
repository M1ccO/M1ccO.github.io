"""Runtime and navigation actions for HomePage.

Keeps module switching, refresh, and selection routing out of home_page.py.
"""

from __future__ import annotations

__all__ = [
    "refresh_catalog",
    "refresh_list",
    "select_tool_by_id",
    "set_active_database_name",
    "set_master_filter",
    "set_module_switch_target",
    "set_page_title",
]


def set_page_title(page, title: str) -> None:
    """Update page title label text."""
    page.page_title = str(title or '')
    if hasattr(page, 'toolbar_title_label'):
        page.toolbar_title_label.setText(page.page_title)


def set_active_database_name(page, db_name: str) -> None:
    """Store active database display name for status/tooltips."""
    page._active_db_name = str(db_name or '').strip()


def set_module_switch_target(page, target: str) -> None:
    """Update module switch button target text and tooltip."""
    target_text = (target or '').strip().upper() or 'JAWS'
    display = (
        page._t('tool_library.module.tools', 'TOOLS')
        if target_text == 'TOOLS'
        else page._t('tool_library.module.fixtures', 'FIXTURES')
        if target_text == 'FIXTURES'
        else page._t('tool_library.module.jaws', 'JAWS')
    )
    if hasattr(page, 'module_toggle_btn'):
        page.module_toggle_btn.setText(display)
        page.module_toggle_btn.setToolTip(
            page._t(
                'tool_library.module.switch_to_target',
                'Switch to {target} module',
                target=display,
            )
        )


def set_master_filter(page, tool_ids, active: bool) -> None:
    """Apply external Setup Manager master filter."""
    page._master_filter_ids = {
        str(t).strip() for t in (tool_ids or []) if str(t).strip()
    }
    page._master_filter_active = bool(active) and bool(page._master_filter_ids)
    page.refresh_list()


def refresh_list(page) -> None:
    """Refresh catalog list (alias for refresh_catalog)."""
    page.refresh_catalog()


def refresh_catalog(page) -> None:
    """Run base catalog refresh and reconnect selection model if needed."""
    super(type(page), page).refresh_catalog()
    page._connect_selection_model()


def select_tool_by_id(page, tool_id: str) -> None:
    """Select a tool by ID and refresh list state."""
    page.current_tool_id = str(tool_id or '').strip() or None
    page.current_tool_uid = None
    page._current_item_id = page.current_tool_id
    page._current_item_uid = None
    page.refresh_list()
