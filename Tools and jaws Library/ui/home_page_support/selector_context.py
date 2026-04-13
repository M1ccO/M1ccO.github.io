"""Selector context helpers for HomePage.

Extracted from home_page.py (Phase 10 Pass 5).
Manages Setup Manager integration: selector state, spindle/head constraints,
assignment buckets, and normalization helpers.
"""

from __future__ import annotations

from ui.selector_state_helpers import (
    normalize_selector_bucket,
    selector_assignments_for_target,
    selector_bucket_map,
)

__all__ = [
    "normalize_selector_tool",
    "selector_tool_key",
    "selector_target_key",
    "selector_current_target_key",
    "tool_matches_selector_spindle",
    "selected_tools_for_setup_assignment",
    "selector_assignment_buckets_for_setup_assignment",
    "selector_current_target_for_setup_assignment",
    "set_selector_context",
    "selector_assigned_tools_for_setup_assignment",
]


def normalize_selector_tool(page, item: dict | None) -> dict | None:
    """Normalize a tool dict for use in selector context."""
    if not isinstance(item, dict):
        return None

    tool_id = str(item.get('tool_id') or item.get('id') or '').strip()
    uid_value = item.get('uid')
    try:
        uid = int(uid_value)
    except Exception:
        uid = 0

    if not tool_id and uid <= 0:
        return None

    head = str(item.get('tool_head') or item.get('head') or page._selector_head or 'HEAD1').strip().upper()
    if head not in {'HEAD1', 'HEAD2'}:
        head = 'HEAD1'

    spindle = str(item.get('spindle') or item.get('spindle_orientation') or page._selector_spindle or 'main').strip().lower()
    if spindle not in {'main', 'sub'}:
        spindle = 'main'

    normalized = dict(item)
    normalized['tool_id'] = tool_id
    normalized['id'] = tool_id
    normalized['uid'] = uid
    normalized['tool_head'] = head
    normalized['spindle'] = spindle
    normalized['spindle_orientation'] = spindle
    return normalized


def selector_tool_key(item: dict | None) -> str:
    """Generate a unique key for a tool dict in selector context."""
    if not isinstance(item, dict):
        return ''
    tool_id = str(item.get('tool_id') or item.get('id') or '').strip()
    uid = str(item.get('uid') or '').strip()
    head = str(item.get('tool_head') or item.get('head') or '').strip().upper()
    spindle = str(item.get('spindle') or item.get('spindle_orientation') or '').strip().lower()
    if tool_id:
        return f'{head}:{spindle}:{tool_id}'
    if uid:
        return f'{head}:{spindle}:uid:{uid}'
    return ''


def selector_target_key(head: str, spindle: str) -> str:
    """Generate a head:spindle target key."""
    normalized_head = str(head or 'HEAD1').strip().upper()
    if normalized_head not in {'HEAD1', 'HEAD2'}:
        normalized_head = 'HEAD1'
    normalized_spindle = str(spindle or 'main').strip().lower()
    if normalized_spindle not in {'main', 'sub'}:
        normalized_spindle = 'main'
    return f'{normalized_head}:{normalized_spindle}'


def selector_current_target_key(page) -> str:
    """Return the target key for the page's current head and spindle."""
    return selector_target_key(page._selector_head, page._selector_spindle)


def tool_matches_selector_spindle(page, tool: dict) -> bool:
    """Return True if the tool is compatible with the selector spindle constraint."""
    if not page._selector_active:
        return True

    spindle = str(
        tool.get('spindle_orientation')
        or tool.get('spindle')
        or tool.get('spindle_side')
        or ''
    ).strip().lower()
    if not spindle:
        return True
    if page._selector_spindle == 'main':
        return spindle in {'main', 'both', 'all'}
    if page._selector_spindle == 'sub':
        return spindle in {'sub', 'both', 'all'}
    return True


def selected_tools_for_setup_assignment(page) -> list[dict]:
    """Return selected tools normalized for setup assignment."""
    selected_items = page.get_selected_items()
    payload: list[dict] = []
    for item in selected_items:
        normalized = normalize_selector_tool(page, item)
        if normalized is None:
            continue
        payload.append(normalized)
    return payload


def selector_assignment_buckets_for_setup_assignment(page) -> dict[str, list[dict]]:
    """Return a copy of all assignment buckets by target key."""
    return {
        key: [dict(item) for item in items if isinstance(item, dict)]
        for key, items in page._selector_assignments_by_target.items()
    }


def selector_current_target_for_setup_assignment(page) -> dict:
    """Return the current target as a head/spindle dict."""
    return {
        'head': page._selector_head,
        'spindle': page._selector_spindle,
    }


def set_selector_context(
    page,
    active: bool,
    head: str = '',
    spindle: str = '',
    initial_assignments: list[dict] | None = None,
    initial_assignment_buckets: dict[str, list[dict]] | None = None,
) -> None:
    """
    Activate or deactivate selector mode.

    Called by Setup Manager when opening tool selector context.

    Args:
        page: HomePage instance
        active: Selector active flag
        head: Target HEAD ('HEAD1', 'HEAD2')
        spindle: Target spindle ('main', 'sub')
        initial_assignments: Initial tool list
        initial_assignment_buckets: Persisted tool buckets by head/spindle
    """
    page._selector_active = bool(active)
    page._selector_head = str(head or 'HEAD1').strip().upper()
    if page._selector_head not in {'HEAD1', 'HEAD2'}:
        page._selector_head = 'HEAD1'

    page._selector_spindle = str(spindle or 'main').strip().lower()
    if page._selector_spindle not in {'main', 'sub'}:
        page._selector_spindle = 'main'

    page._selector_assigned_tools = normalize_selector_bucket(
        initial_assignments,
        lambda item: normalize_selector_tool(page, item),
        selector_tool_key,
    )

    page._selector_assignments_by_target = selector_bucket_map(
        initial_assignment_buckets,
        lambda item: normalize_selector_tool(page, item),
        selector_tool_key,
        selector_target_key,
    )

    target_key = selector_current_target_key(page)
    existing = selector_assignments_for_target(
        page._selector_assignments_by_target,
        target_key,
    )
    if existing:
        page._selector_assigned_tools = existing

    page._selector_assignments_by_target[target_key] = [
        dict(item)
        for item in page._selector_assigned_tools
        if isinstance(item, dict)
    ]

    if hasattr(page, 'selector_bottom_bar') and hasattr(page, 'button_bar'):
        page.selector_bottom_bar.setVisible(page._selector_active)
        page.button_bar.setVisible(not page._selector_active)

    page.refresh_list()


def selector_assigned_tools_for_setup_assignment(page) -> list[dict]:
    """Return persisted tools with head/spindle metadata for setup assignment."""
    target_key = selector_current_target_key(page)
    if page._selector_active:
        page._selector_assignments_by_target[target_key] = [
            dict(item)
            for item in page._selector_assigned_tools
            if isinstance(item, dict)
        ]

    persisted = selector_assignments_for_target(
        page._selector_assignments_by_target,
        target_key,
    )
    return persisted if persisted else selected_tools_for_setup_assignment(page)
