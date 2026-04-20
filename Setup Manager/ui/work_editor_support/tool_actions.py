from __future__ import annotations

from typing import Any


def visible_tool_lists(dialog: Any) -> list:
    is_single = getattr(dialog.machine_profile, 'spindle_count', 0) == 1
    op20_on = getattr(dialog, '_op20_tools_enabled', True)
    visible: list = []
    seen_widget_ids: set[int] = set()
    for columns in dialog._tool_column_lists.values():
        for spindle, ordered in columns.items():
            if is_single and not op20_on and spindle == "sub":
                continue
            obj_id = id(ordered)
            if obj_id in seen_widget_ids:
                continue
            seen_widget_ids.add(obj_id)
            visible.append(ordered)
    return visible


def effective_active_tool_list(dialog: Any):
    if dialog._active_tool_list in visible_tool_lists(dialog):
        return dialog._active_tool_list
    for ordered_list in visible_tool_lists(dialog):
        if ordered_list.tool_list.currentRow() >= 0:
            return ordered_list
    return next(iter(visible_tool_lists(dialog)), None)


def on_tool_list_interaction(dialog: Any, ordered_list) -> None:
    if dialog._syncing_tool_list_state:
        return
    if ordered_list.tool_list.currentRow() >= 0 or ordered_list.tool_list.selectedIndexes():
        set_active_tool_list(dialog, ordered_list)
        return
    if dialog._active_tool_list is ordered_list:
        update_shared_tool_actions(dialog)


def set_active_tool_list(dialog: Any, ordered_list) -> None:
    if ordered_list is None:
        dialog._active_tool_list = None
        update_shared_tool_actions(dialog)
        return
    dialog._syncing_tool_list_state = True
    try:
        dialog._active_tool_list = ordered_list
        # Only one visible column should own selection at a time; this keeps
        # shared action buttons deterministic when both main/sub lists are shown.
        for other in visible_tool_lists(dialog):
            if other is ordered_list:
                continue
            other.tool_list.blockSignals(True)
            other.tool_list.clearSelection()
            other.tool_list.setCurrentRow(-1)
            other.tool_list.blockSignals(False)
            other._sync_row_selection_states()
            other._update_action_states()
    finally:
        dialog._syncing_tool_list_state = False
    ordered_list._sync_row_selection_states()
    ordered_list._update_action_states()
    update_shared_tool_actions(dialog)


def update_shared_tool_actions(dialog: Any) -> None:
    ordered_list = effective_active_tool_list(dialog)
    has_selection = bool(ordered_list and ordered_list.tool_list.currentRow() >= 0)
    current_row = ordered_list.tool_list.currentRow() if ordered_list is not None else -1
    count = ordered_list.tool_list.count() if ordered_list is not None else 0

    dialog.shared_move_up_btn.setEnabled(has_selection and current_row > 0)
    dialog.shared_move_down_btn.setEnabled(has_selection and 0 <= current_row < count - 1)
    dialog.shared_remove_btn.setEnabled(has_selection)


def shared_move_tool_up(dialog: Any) -> None:
    ordered_list = effective_active_tool_list(dialog)
    if ordered_list is None:
        return
    ordered_list._move_up()
    update_shared_tool_actions(dialog)


def shared_move_tool_down(dialog: Any) -> None:
    ordered_list = effective_active_tool_list(dialog)
    if ordered_list is None:
        return
    ordered_list._move_down()
    update_shared_tool_actions(dialog)


def shared_remove_selected_tool(dialog: Any) -> None:
    ordered_list = effective_active_tool_list(dialog)
    if ordered_list is None:
        return
    ordered_list._remove_selected()
    update_shared_tool_actions(dialog)


def remove_dragged_tool_assignments(dialog: Any, dropped_items: list[dict]) -> None:
    affected_list = None
    for head_key, columns in dialog._tool_column_lists.items():
        for spindle in ("main", "sub"):
            target_list = columns.get(spindle)
            if target_list is None:
                continue
            keys = []
            for item in (dropped_items or []):
                if not isinstance(item, dict):
                    continue
                item_spindle = dialog._normalize_selector_spindle(item.get("spindle"))
                if item_spindle != spindle:
                    continue
                item_head = dialog._normalize_selector_head(item.get("head") or item.get("head_key") or "")
                if item_head and item_head != head_key:
                    continue
                key = target_list._assignment_key(item)
                if key:
                    keys.append(key)
            if keys:
                target_list._remove_assignments_by_keys(keys)
                affected_list = target_list
    if affected_list is not None:
        set_active_tool_list(dialog, affected_list)
    else:
        update_shared_tool_actions(dialog)


def refresh_tool_head_widgets(dialog: Any, head_key: str) -> None:
    columns = dialog._tool_column_lists.get(dialog._normalize_selector_head(head_key), {})
    for spindle, ordered_list in columns.items():
        ordered_list.set_current_spindle(spindle)
        ordered_list._render_current_spindle()


def sync_tool_head_view(dialog: Any) -> None:
    is_single = getattr(dialog.machine_profile, 'spindle_count', 0) == 1
    op20_on = getattr(dialog, '_op20_tools_enabled', True)
    processed_widget_ids: set[int] = set()
    for _head_key, columns in dialog._tool_column_lists.items():
        for spindle, ordered_list in columns.items():
            obj_id = id(ordered_list)
            if obj_id in processed_widget_ids:
                continue
            processed_widget_ids.add(obj_id)
            ordered_list.set_current_spindle(spindle)
            col_visible = spindle != "sub" or not is_single or op20_on
            ordered_list.setVisible(col_visible)
            if col_visible:
                ordered_list._render_current_spindle()

    visible_lists = visible_tool_lists(dialog)
    preferred_active = None
    for candidate in visible_lists:
        if candidate.tool_list.currentRow() >= 0:
            preferred_active = candidate
            break
    if preferred_active is None and visible_lists:
        preferred_active = visible_lists[0]
    if preferred_active is not None:
        set_active_tool_list(dialog, preferred_active)
    else:
        update_shared_tool_actions(dialog)


def default_pot_for_assignment(ordered_list, assignment: dict) -> str:
    # Try resolver-primary path first (via _tool_ref_for_assignment which
    # already prefers _direct_tool_ref_resolver over _all_tools).
    ref = ordered_list._tool_ref_for_assignment(assignment)
    if isinstance(ref, dict) and str(ref.get("default_pot") or "").strip():
        return str(ref["default_pot"]).strip()

    # Fall back to _all_tools cache scan (legacy path, kept until resolver
    # covers all assignment contexts).
    assignment_key = ordered_list._assignment_key(assignment)
    tool_id = (assignment.get("tool_id") or "").strip()
    for tool in ordered_list._all_tools or []:
        if not isinstance(tool, dict):
            continue
        tool_key = ordered_list._assignment_key(
            {
                "tool_id": (tool.get("id") or "").strip(),
                "tool_uid": tool.get("uid"),
            }
        )
        if tool_key == assignment_key:
            return str(tool.get("default_pot") or "").strip()
    if not tool_id:
        return ""
    for tool in ordered_list._all_tools or []:
        if not isinstance(tool, dict):
            continue
        if str(tool.get("id") or "").strip() == tool_id:
            return str(tool.get("default_pot") or "").strip()
    return ""


def populate_default_pots(dialog: Any) -> None:
    changed = False
    for ordered_list in dialog._ordered_tool_lists.values():
        for spindle in dialog._spindle_profiles.keys():
            for assignment in ordered_list._assignments_by_spindle.get(spindle, []):
                if (assignment.get("pot") or "").strip():
                    continue
                candidate = default_pot_for_assignment(ordered_list, assignment)
                if candidate:
                    assignment["pot"] = candidate
                    changed = True
    if changed:
        for ordered_list in dialog._all_tool_list_widgets:
            ordered_list._render_current_spindle()
