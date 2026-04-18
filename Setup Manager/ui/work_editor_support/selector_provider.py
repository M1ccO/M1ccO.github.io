from __future__ import annotations

from typing import Any

from .selectors import (
    normalize_selector_head,
    normalize_selector_spindle,
    selector_initial_tool_assignment_buckets,
    selector_initial_tool_assignments,
)
from .selector_state import (
    default_jaw_selector_spindle,
    default_selector_head,
    default_selector_spindle,
    selector_target_ordered_list,
)


def _dialog_default_selector_head(dialog: Any) -> str:
    legacy = getattr(dialog, "_default_selector_head", None)
    if callable(legacy):
        return str(legacy() or "")
    return default_selector_head(dialog)


def _dialog_default_selector_spindle(dialog: Any) -> str:
    legacy = getattr(dialog, "_default_selector_spindle", None)
    if callable(legacy):
        return str(legacy() or "")
    return default_selector_spindle(dialog)


def _dialog_default_jaw_selector_spindle(dialog: Any) -> str:
    legacy = getattr(dialog, "_default_jaw_selector_spindle", None)
    if callable(legacy):
        return str(legacy() or "")
    return default_jaw_selector_spindle(dialog)


def build_initial_jaw_assignments(dialog: Any) -> list[dict]:
    assignments: list[dict] = []
    jaws_by_id: dict[str, dict] = {
        str(jaw.get("id") or jaw.get("jaw_id") or "").strip(): jaw
        for jaw in (dialog._jaw_cache or [])
        if isinstance(jaw, dict) and str(jaw.get("id") or jaw.get("jaw_id") or "").strip()
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


def build_tool_selector_request(
    dialog: Any,
    *,
    initial_head: str | None = None,
    initial_spindle: str | None = None,
    initial_assignments: list[dict] | None = None,
) -> dict:
    """Build normalized request payload inputs for tool selector sessions."""
    resolved_head = normalize_selector_head(initial_head or _dialog_default_selector_head(dialog))
    resolved_spindle = normalize_selector_spindle(initial_spindle or _dialog_default_selector_spindle(dialog))

    assignments = list(initial_assignments or [])
    if not assignments:
        ordered_list = selector_target_ordered_list(dialog, resolved_head)
        assignments = selector_initial_tool_assignments(ordered_list, resolved_spindle)

    buckets = selector_initial_tool_assignment_buckets(
        dialog._tool_column_lists,
        tuple(dialog._head_profiles.keys()),
        tuple(dialog._spindle_profiles.keys()),
    )

    return {
        "kind": "tools",
        "head": resolved_head,
        "spindle": resolved_spindle,
        "initial_assignments": assignments,
        "initial_assignment_buckets": buckets,
    }


def build_jaw_selector_request(dialog: Any, *, initial_spindle: str | None = None) -> dict:
    """Build normalized request payload inputs for jaw selector sessions."""
    return {
        "kind": "jaws",
        "spindle": normalize_selector_spindle(initial_spindle or _dialog_default_jaw_selector_spindle(dialog)),
        "initial_assignments": build_initial_jaw_assignments(dialog),
    }


def build_fixture_selector_request(dialog: Any, *, operation_key: str | None = None) -> dict:
    """Build normalized request payload inputs for fixture selector sessions."""
    buckets: dict[str, list[dict]] = {}
    for op in getattr(dialog, "_mc_operations", []) or []:
        if not isinstance(op, dict):
            continue
        op_key = str(op.get("op_key") or "").strip()
        if not op_key:
            continue
        buckets[op_key] = [dict(item) for item in (op.get("fixture_items") or []) if isinstance(item, dict)]

    target_key = str(operation_key or "").strip()
    if not target_key:
        target_key = next(iter(buckets.keys()), "")

    return {
        "kind": "fixtures",
        "follow_up": {"target_key": target_key},
        "initial_assignments": list(buckets.get(target_key) or []),
        "initial_assignment_buckets": buckets,
    }
