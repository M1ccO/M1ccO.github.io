"""Pure normalization helpers for the selector tool model."""

from __future__ import annotations

from ui.selector_ui_helpers import normalize_selector_spindle


def selector_tool_key(tool: dict | None) -> str:
    """Return a stable string key for a tool assignment dict.

    Prefers ``uid``-based keys when a uid is present so that renamed tools
    still resolve correctly.
    """
    if not isinstance(tool, dict):
        return ''
    tool_uid = tool.get('tool_uid', tool.get('uid'))
    if tool_uid is not None and str(tool_uid).strip():
        return f'uid:{tool_uid}'
    tool_id = str(tool.get('tool_id') or tool.get('id') or '').strip()
    return f'id:{tool_id}' if tool_id else ''


def normalize_selector_tool(tool: dict | None) -> dict | None:
    """Normalize a raw tool dict into canonical selector assignment shape.

    Returns ``None`` when the dict has no usable tool_id.
    """
    if not isinstance(tool, dict):
        return None
    tool_id = str(tool.get('tool_id') or tool.get('id') or '').strip()
    if not tool_id:
        return None
    normalized: dict = {'tool_id': tool_id}
    tool_uid = tool.get('tool_uid', tool.get('uid'))
    try:
        parsed_uid = int(tool_uid) if tool_uid is not None and str(tool_uid).strip() else None
    except Exception:
        parsed_uid = None
    if parsed_uid is not None:
        normalized['tool_uid'] = parsed_uid
    for key in ('description', 'tool_type', 'default_pot'):
        value = str(tool.get(key) or '').strip()
        if value:
            normalized[key] = value
    comment = str(tool.get('comment') or '').strip()
    if comment:
        normalized['comment'] = comment
    return normalized


def normalize_selector_head_value(head: str) -> str:
    """Normalize a head filter string to 'HEAD1' or 'HEAD2'."""
    return 'HEAD2' if str(head or '').strip().upper() == 'HEAD2' else 'HEAD1'


def normalize_selector_spindle_value(spindle: str) -> str:
    """Normalize a spindle string to 'main' or 'sub'."""
    return normalize_selector_spindle(spindle)


def normalize_tool_spindle_orientation(value: str | None) -> str:
    """Map a raw spindle_orientation field to 'main', 'sub', or 'both'."""
    raw = str(value or '').strip().lower().replace('_', ' ')
    if not raw:
        return 'main'
    if 'both' in raw:
        return 'both'
    if raw in {'sub', 'sub spindle', 'subspindle', 'counter spindle'}:
        return 'sub'
    return 'main'


def selector_target_key(head: str, spindle: str) -> str:
    """Build the target bucket key from head and spindle values."""
    return f"{normalize_selector_head_value(head)}:{normalize_selector_spindle_value(spindle)}"


__all__ = [
    "normalize_selector_head_value",
    "normalize_selector_spindle_value",
    "normalize_selector_tool",
    "normalize_tool_spindle_orientation",
    "selector_target_key",
    "selector_tool_key",
]
