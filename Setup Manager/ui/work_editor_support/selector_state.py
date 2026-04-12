from __future__ import annotations

from typing import Any


def selector_target_ordered_list(dialog: Any, head_key: str):
    normalized = dialog._normalize_selector_head(head_key)
    if normalized in dialog._ordered_tool_lists:
        return dialog._ordered_tool_lists[normalized]
    return next(iter(dialog._ordered_tool_lists.values()))


def default_selector_spindle(dialog: Any) -> str:
    current_head = current_tools_head_value(dialog)
    head_columns = dialog._tool_column_lists.get(current_head, {})
    for spindle in ("main", "sub"):
        ordered = head_columns.get(spindle)
        if ordered is not None and hasattr(ordered, "tool_list") and ordered.tool_list.hasFocus():
            return spindle
    return dialog.machine_profile.default_tools_spindle


def current_tools_head_value(dialog: Any) -> str:
    if not hasattr(dialog, "tools_head_switch"):
        return next(iter(dialog._head_profiles.keys()), "HEAD1")
    return dialog._normalize_selector_head(
        dialog.tools_head_switch.property("head") or next(iter(dialog._head_profiles.keys()), "HEAD1")
    )


def update_tools_head_switch_text(dialog: Any) -> None:
    if not hasattr(dialog, "tools_head_switch"):
        return
    head = current_tools_head_value(dialog)
    head_profile = dialog._head_profiles.get(head)
    label = dialog._head_label(head, head_profile.label_default if head_profile else head)
    dialog.tools_head_switch.setText(label)
    dialog.tools_head_switch.setChecked(head == "HEAD2")


def set_tools_head_value(dialog: Any, head: str) -> None:
    normalized = dialog._normalize_selector_head(head)
    if not hasattr(dialog, "tools_head_switch"):
        return
    dialog.tools_head_switch.setProperty("head", normalized)
    update_tools_head_switch_text(dialog)


def toggle_tools_head_view(dialog: Any) -> None:
    if not hasattr(dialog, "tools_head_switch"):
        return
    target = "HEAD2" if dialog.tools_head_switch.isChecked() else "HEAD1"
    set_tools_head_value(dialog, target)
    dialog._sync_tool_head_view()


def default_selector_head(dialog: Any) -> str:
    for head_key, columns in dialog._tool_column_lists.items():
        for ordered_list in columns.values():
            if hasattr(ordered_list, "tool_list") and ordered_list.tool_list.hasFocus():
                return head_key
    return current_tools_head_value(dialog)


def default_jaw_selector_spindle(dialog: Any) -> str:
    for spindle_key, selector in dialog._jaw_selectors.items():
        focus_widget = selector.focusWidget()
        if focus_widget is not None and selector.isAncestorOf(focus_widget):
            return spindle_key
    return default_selector_spindle(dialog)
