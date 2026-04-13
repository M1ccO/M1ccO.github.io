"""Filter coordination for HomePage catalog queries."""

from __future__ import annotations

from ui.tool_catalog_delegate import tool_icon_for_type

__all__ = ["apply_filters", "view_match"]


def view_match(page, tool: dict) -> bool:
    """Check if a tool matches current view mode."""
    mode = (page.view_mode or 'home').strip().lower()
    if mode in {'home', 'tools'}:
        return True
    if mode == 'holders':
        return bool(str(tool.get('holder_code', '')).strip())
    if mode == 'inserts':
        return bool(str(tool.get('cutting_code', '')).strip())
    if mode == 'assemblies':
        return bool(tool.get('component_items') or tool.get('support_parts') or tool.get('stl_path'))
    return True


def apply_filters(page, filters: dict) -> list[dict]:
    """Query tool service and apply all HomePage filter constraints."""
    search_text = filters.get('search', '').strip()
    tool_type = filters.get('tool_type', 'All')
    tool_head = filters.get('tool_head', page._selected_head_filter())

    tools = page.tool_service.list_tools(
        search_text=search_text,
        tool_type=tool_type,
        tool_head=tool_head,
    )

    if page._selector_active:
        tools = [
            tool for tool in tools
            if page._tool_matches_selector_spindle(tool)
        ]

    if page._master_filter_active:
        tools = [
            tool for tool in tools
            if str(tool.get('id', '')).strip() in page._master_filter_ids
        ]

    tools = [tool for tool in tools if view_match(page, tool)]

    catalog_items: list[dict] = []
    for tool in tools:
        item = dict(tool)
        item['id'] = str(item.get('id', '')).strip()
        try:
            item['uid'] = int(item.get('uid', 0) or 0)
        except Exception:
            item['uid'] = 0
        item['icon'] = tool_icon_for_type(str(item.get('tool_type', '') or ''))
        catalog_items.append(item)

    return catalog_items
