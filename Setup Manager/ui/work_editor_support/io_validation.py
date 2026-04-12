from __future__ import annotations

from typing import Any

from .selectors import load_external_tool_refs


def refresh_external_refs(dialog: Any) -> None:
    """Refresh tool/jaw master caches and push them to visible selectors/lists."""
    # Keep selector caches head-aware so future machine profiles can expose
    # different stations without duplicating lookup/merge rules in the dialog.
    dialog._tool_cache_by_head, dialog._tool_cache_all = load_external_tool_refs(
        dialog.draw_service,
        tuple(dialog._head_profiles.keys()),
    )
    dialog._jaw_cache = dialog.draw_service.list_jaw_refs(force_reload=True)

    for selector in dialog._jaw_selectors.values():
        selector.populate(dialog._jaw_cache)
    for head_key, columns in dialog._tool_column_lists.items():
        refs = dialog._tool_cache_by_head.get(head_key, dialog._tool_cache_all)
        for ordered_list in columns.values():
            ordered_list._all_tools = refs


def collect_unresolved_reference_messages(dialog: Any) -> list[str]:
    tool_ids = {item["id"] for item in (dialog._tool_cache_all or []) if item.get("id")}
    jaw_ids = {item["id"] for item in (dialog._jaw_cache or []) if item.get("id")}

    missing: list[str] = []
    for spindle_key, selector in dialog._jaw_selectors.items():
        jaw_key = dialog._spindle_label(spindle_key, spindle_key)
        jaw_value = selector.get_value()
        if jaw_value and jaw_ids and jaw_value not in jaw_ids:
            missing.append(f"{jaw_key}: {jaw_value}")

    for head_key, ordered_list in dialog._ordered_tool_lists.items():
        head_name = dialog._head_label(head_key, head_key)
        for tool_id in ordered_list.get_tool_ids():
            if tool_ids and tool_id not in tool_ids:
                missing.append(f"{head_name}: {tool_id}")

    return missing
