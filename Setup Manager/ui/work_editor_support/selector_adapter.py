from __future__ import annotations

from typing import Any

from .bridge_actions import open_external_selector_session, show_selector_warning
from .selectors import (
    apply_fixture_selector_items_to_operations,
    apply_jaw_selector_items_to_selectors,
    apply_tool_selector_items_to_ordered_list,
    merge_jaw_refs_and_sync_selectors,
    merge_tool_refs_and_sync_lists,
    normalize_selector_head,
    normalize_selector_spindle,
)


def head_label(dialog: Any, head_key: str, fallback: str | None = None) -> str:
    profile = dialog._head_profiles.get(normalize_selector_head(head_key))
    default = fallback or (profile.label_default if profile is not None else head_key)
    if profile is None:
        return default
    return dialog._t(profile.label_key, default)


def spindle_label(dialog: Any, spindle_key: str, fallback: str | None = None) -> str:
    profile = dialog._spindle_profiles.get(normalize_selector_spindle(spindle_key))
    # Profile's own label_default always takes precedence; fallback is only used
    # when the profile is completely absent (unknown spindle key).
    if profile is None:
        return fallback or spindle_key
    default = profile.label_default
    return dialog._t(profile.label_key, default)


def merge_tool_refs(dialog: Any, head_key: str, selected_items: list[dict]) -> None:
    target_head = normalize_selector_head(head_key)
    dialog._tool_cache_by_head, dialog._tool_cache_all = merge_tool_refs_and_sync_lists(
        dialog._tool_cache_by_head,
        dialog._tool_cache_all,
        head_key=target_head,
        selected_items=selected_items,
        tool_column_lists=dialog._tool_column_lists,
    )


def merge_jaw_refs(dialog: Any, selected_items: list[dict]) -> None:
    jaw_refs, changed = merge_jaw_refs_and_sync_selectors(
        dialog._jaw_cache,
        selected_items,
        dialog._jaw_selectors,
    )
    if changed:
        dialog._jaw_cache = jaw_refs


def apply_tool_selector_result(dialog: Any, request: dict, selected_items: list[dict]) -> bool:
    head_key = normalize_selector_head(request.get("head"))
    spindle = normalize_selector_spindle(request.get("spindle"))
    ordered_list = dialog._selector_target_ordered_list(head_key)
    merge_tool_refs(dialog, head_key, selected_items)

    apply_tool_selector_items_to_ordered_list(
        ordered_list,
        selected_items,
        spindle=spindle,
    )

    dialog._set_tools_head_value(head_key)
    dialog._sync_tool_head_view()
    dialog._refresh_tool_head_widgets(head_key)
    return True


def apply_jaw_selector_result(dialog: Any, request: dict, selected_items: list[dict]) -> bool:
    spindle = normalize_selector_spindle(request.get("spindle"))
    merge_jaw_refs(dialog, selected_items)
    return apply_jaw_selector_items_to_selectors(
        dialog._jaw_selectors,
        selected_items,
        target_spindle=spindle,
        normalize_spindle_fn=normalize_selector_spindle,
    )


def apply_fixture_selector_result(dialog: Any, request: dict, selected_items: list[dict]) -> bool:
    return apply_fixture_selector_items_to_operations(
        dialog,
        request=request,
        selected_items=selected_items,
    )


def show_selector_warning_for_dialog(dialog: Any, title: str, body: str) -> None:
    show_selector_warning(dialog, title, body)


def open_external_selector_session_for_dialog(
    dialog: Any,
    *,
    kind: str,
    head: str | None = None,
    spindle: str | None = None,
    follow_up: dict | None = None,
    initial_assignments: list[dict] | None = None,
    initial_assignment_buckets: dict[str, list[dict]] | None = None,
) -> bool:
    return open_external_selector_session(
        dialog,
        kind=kind,
        head=head,
        spindle=spindle,
        follow_up=follow_up,
        initial_assignments=initial_assignments,
        initial_assignment_buckets=initial_assignment_buckets,
    )
