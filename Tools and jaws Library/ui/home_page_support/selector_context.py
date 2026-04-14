"""Selector context helpers for HomePage.

Pure data helpers used by the HomePage to support Setup Manager integration.
The full selector UI (assignment list, panel show/hide, spindle toggle) now
lives inside ToolSelectorDialog / JawSelectorDialog — these are the only
functions that the page itself still needs.
"""

from __future__ import annotations

__all__ = [
    "normalize_selector_tool",
    "selector_tool_key",
    "selector_target_key",
    "tool_matches_selector_spindle",
]


def normalize_selector_tool(page, item: dict | None) -> dict | None:
    """Normalize a tool dict for use in selector context.

    Returns None if the item lacks a usable tool_id or uid.
    """
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

    spindle = str(
        item.get('spindle') or item.get('spindle_orientation') or page._selector_spindle or 'main'
    ).strip().lower()
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
    """Return a unique string key for *item* within a selector bucket.

    Format: ``HEAD1:main:T001`` (by tool_id) or ``HEAD1:main:uid:42`` (by uid).
    Empty string means the item is not keyed (invalid or empty).
    """
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
    """Return a normalised ``HEAD1:main``-style target key."""
    normalized_head = str(head or 'HEAD1').strip().upper()
    if normalized_head not in {'HEAD1', 'HEAD2'}:
        normalized_head = 'HEAD1'
    normalized_spindle = str(spindle or 'main').strip().lower()
    if normalized_spindle not in {'main', 'sub'}:
        normalized_spindle = 'main'
    return f'{normalized_head}:{normalized_spindle}'


def tool_matches_selector_spindle(page, tool: dict) -> bool:
    """Return True if *tool* is compatible with the page's active spindle constraint.

    Always returns True when the page is not in selector mode.
    """
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
