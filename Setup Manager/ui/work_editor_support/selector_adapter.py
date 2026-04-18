from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QMessageBox
from .selectors import (
    apply_fixture_selector_items_to_operations,
    apply_jaw_selector_items_to_selectors,
    apply_tool_selector_items_to_ordered_list,
    merge_jaw_refs_and_sync_selectors,
    merge_tool_refs_and_sync_lists,
    normalize_selector_head,
    normalize_selector_spindle,
)
from .selector_state import selector_target_ordered_list, set_tools_head_value


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
    # Resolver-backed rendering is now primary. Legacy cache merging remains an
    # optional fallback path for callers that explicitly opt in.
    if not bool(getattr(dialog, "_selector_cache_merge_enabled", False)):
        return
    target_head = normalize_selector_head(head_key)
    dialog._tool_cache_by_head, dialog._tool_cache_all = merge_tool_refs_and_sync_lists(
        dialog._tool_cache_by_head,
        dialog._tool_cache_all,
        head_key=target_head,
        selected_items=selected_items,
        tool_column_lists=dialog._tool_column_lists,
    )


def merge_jaw_refs(dialog: Any, selected_items: list[dict]) -> None:
    if not bool(getattr(dialog, "_selector_cache_merge_enabled", False)):
        return
    jaw_refs, changed = merge_jaw_refs_and_sync_selectors(
        dialog._jaw_cache,
        selected_items,
        dialog._jaw_selectors,
    )
    if changed:
        dialog._jaw_cache = jaw_refs


def _tool_assignment_buckets_from_request(
    request: dict | None,
    selected_items: list[dict],
) -> dict[tuple[str, str], list[dict]]:
    payload = request if isinstance(request, dict) else {}
    raw_buckets = payload.get("assignment_buckets_by_target")
    normalized: dict[tuple[str, str], list[dict]] = {}

    if isinstance(raw_buckets, dict):
        for raw_target, raw_items in raw_buckets.items():
            target = str(raw_target or "").strip()
            if not target or ":" not in target:
                continue
            head_text, spindle_text = target.split(":", 1)
            head_key = normalize_selector_head(head_text)
            spindle_key = normalize_selector_spindle(spindle_text)
            items = [dict(item) for item in (raw_items or []) if isinstance(item, dict)]
            normalized[(head_key, spindle_key)] = items

    if normalized:
        return normalized

    head_key = normalize_selector_head(payload.get("head"))
    spindle_key = normalize_selector_spindle(payload.get("spindle"))
    fallback_items = [dict(item) for item in (selected_items or []) if isinstance(item, dict)]
    return {(head_key, spindle_key): fallback_items}


def apply_tool_selector_result(dialog: Any, request: dict, selected_items: list[dict]) -> bool:
    head_key = normalize_selector_head(request.get("head"))
    assignment_buckets = _tool_assignment_buckets_from_request(request, selected_items)

    for (bucket_head, bucket_spindle), bucket_items in assignment_buckets.items():
        ordered_list = (
            ((dialog._tool_column_lists.get(bucket_head) or {}).get(bucket_spindle))
            or selector_target_ordered_list(dialog, bucket_head)
        )
        merge_tool_refs(dialog, bucket_head, bucket_items)
        apply_tool_selector_items_to_ordered_list(
            ordered_list,
            bucket_items,
            spindle=bucket_spindle,
        )

    legacy_set_head = getattr(dialog, "_set_tools_head_value", None)
    if callable(legacy_set_head):
        legacy_set_head(head_key)
    else:
        set_tools_head_value(dialog, head_key)
    dialog._sync_tool_head_view()
    refresh_heads = list(getattr(dialog, "_head_profiles", {}).keys()) or list(
        getattr(dialog, "_tool_column_lists", {}).keys()
    )
    for refresh_head in refresh_heads:
        dialog._refresh_tool_head_widgets(refresh_head)
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
    QMessageBox.warning(dialog, title, body)
