from __future__ import annotations

from typing import Any


def build_initial_jaw_assignments(dialog: Any) -> list[dict]:
    assignments: list[dict] = []
    jaws_by_id: dict[str, dict] = {
        str(jaw.get("id") or "").strip(): jaw
        for jaw in (dialog._jaw_cache or [])
        if isinstance(jaw, dict) and str(jaw.get("id") or "").strip()
    }
    for spindle_key in ("main", "sub"):
        selector = dialog._jaw_selectors.get(spindle_key)
        if selector is None:
            continue
        jaw_id = str(selector.get_value() or "").strip()
        if not jaw_id:
            continue
        jaw_ref = jaws_by_id.get(jaw_id, {})
        entry = {
            "jaw_id": jaw_id,
            "spindle": spindle_key,
        }
        jaw_type = str(jaw_ref.get("jaw_type") or "").strip()
        if jaw_type:
            entry["jaw_type"] = jaw_type
        description = str(jaw_ref.get("description") or "").strip()
        if description:
            entry["description"] = description
        assignments.append(entry)
    return assignments


def open_tool_selector_session(
    dialog: Any,
    *,
    initial_head: str | None = None,
    initial_spindle: str | None = None,
    initial_assignments: list[dict] | None = None,
) -> bool:
    dialog._load_external_refs()
    resolved_head = initial_head or dialog._default_selector_head()
    resolved_spindle = initial_spindle or dialog._default_selector_spindle()
    if initial_assignments is None:
        initial_assignments = dialog._selector_initial_tool_assignments(resolved_head, resolved_spindle)
    return dialog._open_external_selector_session(
        kind="tools",
        head=resolved_head,
        spindle=resolved_spindle,
        initial_assignments=initial_assignments,
    )


def open_jaw_selector_session(dialog: Any, *, initial_spindle: str | None = None) -> bool:
    dialog._load_external_refs()
    return dialog._open_external_selector_session(
        kind="jaws",
        spindle=initial_spindle or dialog._default_jaw_selector_spindle(),
        initial_assignments=build_initial_jaw_assignments(dialog),
    )


def open_fixture_selector_session(dialog: Any, *, operation_key: str, initial_assignments: list[dict] | None = None) -> bool:
    return dialog._open_external_selector_session(
        kind='fixtures',
        follow_up={'target_key': operation_key},
        initial_assignments=initial_assignments or [],
    )


def open_combined_tools_jaws_selector_session(dialog: Any) -> None:
    spindle = dialog._default_selector_spindle()
    default_head = dialog._default_selector_head()
    # Keep tool->jaw chaining in one place so follow-up payload stays aligned
    # if profile-driven defaults for spindle/head evolve later.
    dialog._open_external_selector_session(
        kind="tools",
        head=default_head,
        spindle=spindle,
        follow_up={"kind": "jaws", "spindle": spindle},
        initial_assignments=dialog._selector_initial_tool_assignments(default_head, spindle),
    )
