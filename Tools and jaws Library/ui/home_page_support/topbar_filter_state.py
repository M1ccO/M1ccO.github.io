"""Head filter state helpers for HomePage.

Extracted from home_page.py (Phase 10 Pass 2).
Functions manage the external head-filter widget binding and current filter value.
"""

from __future__ import annotations

__all__ = [
    "selected_head_filter",
    "bind_external_head_filter",
    "set_head_filter_value",
]


def _profile_head_keys(page) -> list[str]:
    profile = getattr(page, 'machine_profile', None)
    heads = []
    if isinstance(profile, dict):
        heads = profile.get('heads') or []
    elif profile is not None:
        heads = getattr(profile, 'heads', ()) or ()

    keys: list[str] = []
    for head in heads:
        if isinstance(head, dict):
            key = str(head.get('key') or '').strip().upper()
        else:
            key = str(getattr(head, 'key', '') or '').strip().upper()
        if key and key not in keys:
            keys.append(key)

    return keys or ['HEAD1', 'HEAD2']


def selected_head_filter(page) -> str:
    """Return the active head filter value (from external widget or internal state)."""
    valid_heads = _profile_head_keys(page)
    allow_combined = len(valid_heads) > 1
    if page._external_head_filter:
        try:
            external_value = page._external_head_filter.currentData()
        except Exception:
            external_value = None
        if external_value is not None:
            raw = str(external_value).strip().upper()
            if raw in valid_heads:
                return raw
            if allow_combined and raw == 'HEAD1/2':
                return raw
    raw = str(page._head_filter_value or '').strip().upper()
    if raw in valid_heads:
        return raw
    if allow_combined and raw == 'HEAD1/2':
        return raw
    return 'HEAD1/2' if allow_combined else valid_heads[0]


def bind_external_head_filter(page, head_filter_widget) -> None:
    """Bind a shared rail head-filter control from MainWindow."""
    page._external_head_filter = head_filter_widget


def set_head_filter_value(page, value: str, refresh: bool = True) -> None:
    """Set the active head filter value and optionally refresh the catalog list."""
    valid_heads = _profile_head_keys(page)
    allow_combined = len(valid_heads) > 1
    fallback = 'HEAD1/2' if allow_combined else valid_heads[0]
    normalized = str(value or fallback).strip().upper()
    allowed_values = set(valid_heads)
    if allow_combined:
        allowed_values.add('HEAD1/2')
    if normalized not in allowed_values:
        normalized = fallback

    page._head_filter_value = normalized

    if page._external_head_filter is not None:
        setter = getattr(page._external_head_filter, 'setCurrentData', None)
        if callable(setter):
            try:
                setter(normalized, emit_signal=False)
            except TypeError:
                setter(normalized)
            except Exception:
                pass

    if refresh:
        page.refresh_list()
