from __future__ import annotations

from typing import Callable


SELECTOR_SLOT_KEYS: tuple[str, str] = ("main", "sub")


def normalize_selector_mode(mode: str | None) -> str:
    return "details" if str(mode or "").strip().lower() == "details" else "selector"


def default_selector_splitter_sizes(total_width: int) -> list[int]:
    total = max(600, int(total_width or 0))
    return [int(total * 0.62), int(total * 0.38)]


def selector_target_parts(
    raw_key: str | None,
    *,
    default_head: str = "HEAD1",
    default_spindle: str = "main",
) -> tuple[str, str]:
    text = str(raw_key or "").strip()
    if ":" in text:
        return tuple(text.split(":", 1))
    if "/" in text:
        return tuple(text.split("/", 1))
    return default_head, default_spindle


def normalize_selector_bucket(
    items: list[dict] | None,
    normalize_item: Callable[[dict | None], dict | None],
    item_key: Callable[[dict | None], str],
) -> list[dict]:
    # Selector payloads can arrive from different pages and older call sites.
    # We normalize once here so each UI only renders clean, de-duplicated items.
    normalized_items: list[dict] = []
    seen_keys: set[str] = set()
    for item in items or []:
        normalized = normalize_item(item)
        if normalized is None:
            continue
        key = item_key(normalized)
        if key and key in seen_keys:
            continue
        if key:
            seen_keys.add(key)
        normalized_items.append(normalized)
    return normalized_items


def selector_bucket_map(
    raw_buckets: dict[str, list[dict]] | None,
    normalize_item: Callable[[dict | None], dict | None],
    item_key: Callable[[dict | None], str],
    build_target_key: Callable[[str, str], str],
) -> dict[str, list[dict]]:
    loaded_buckets: dict[str, list[dict]] = {}
    if not isinstance(raw_buckets, dict):
        return loaded_buckets
    for raw_key, raw_items in raw_buckets.items():
        if not isinstance(raw_items, list):
            continue
        head_part, spindle_part = selector_target_parts(raw_key)
        target_key = build_target_key(head_part, spindle_part)
        loaded_buckets[target_key] = normalize_selector_bucket(raw_items, normalize_item, item_key)
    return loaded_buckets


def selector_assignments_for_target(
    assignments_by_target: dict[str, list[dict]],
    target_key: str,
) -> list[dict]:
    return [dict(item) for item in assignments_by_target.get(target_key, []) if isinstance(item, dict)]


def slot_assignments_state(
    assignments: dict[str, dict | None] | None,
    *,
    slot_keys: tuple[str, ...] = SELECTOR_SLOT_KEYS,
) -> dict[str, dict | None]:
    # Keep the slot map stable even when a caller provides partial or stale data.
    state = {slot: None for slot in slot_keys}
    if not isinstance(assignments, dict):
        return state
    for slot in slot_keys:
        value = assignments.get(slot)
        state[slot] = value if isinstance(value, dict) else None
    return state


def prune_selected_slots(
    selected_slots: set[str] | list[str] | tuple[str, ...],
    assignments: dict[str, dict | None],
) -> set[str]:
    return {slot for slot in set(selected_slots or ()) if assignments.get(slot) is not None}


def toggle_selector_slot_selection(
    selected_slots: set[str] | list[str] | tuple[str, ...],
    slot: str,
    *,
    has_assignment: bool,
    ctrl_pressed: bool,
) -> set[str]:
    next_selected = set(selected_slots or ())
    if not has_assignment:
        if not ctrl_pressed:
            next_selected.clear()
        return next_selected
    if ctrl_pressed:
        if slot in next_selected:
            next_selected.remove(slot)
        else:
            next_selected.add(slot)
        return next_selected
    return {slot}


def has_any_selector_assignment(
    assignments: dict[str, dict | None],
    *,
    slot_keys: tuple[str, ...] = SELECTOR_SLOT_KEYS,
) -> bool:
    return any(assignments.get(slot) is not None for slot in slot_keys)


def normalized_slot_payload(
    assignments: dict[str, dict | None],
    normalize_item: Callable[[dict | None], dict | None],
    *,
    slot_keys: tuple[str, ...] = SELECTOR_SLOT_KEYS,
) -> list[dict]:
    payload: list[dict] = []
    for slot in slot_keys:
        normalized = normalize_item(assignments.get(slot))
        if normalized is not None:
            payload.append(normalized)
    return payload
