"""Selector action helpers for HomePage."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QInputDialog

from shared.ui.cards.mini_assignment_card import MiniAssignmentCard


def update_selector_assignment_buttons(page) -> None:
    if not hasattr(page, "selector_remove_btn"):
        return
    selected_rows = page._selector_selected_rows()
    has_row = bool(selected_rows)
    single_selected = len(selected_rows) == 1
    current_row = selected_rows[0] if single_selected else -1
    has_items = bool(getattr(page, "selector_assignment_list", None) and page.selector_assignment_list.count() > 0)
    assignment = None
    if single_selected and 0 <= current_row < len(page._selector_assigned_tools):
        assignment = page._selector_assigned_tools[current_row]
    has_comment = bool(str((assignment or {}).get("comment") or "").strip())
    page.selector_remove_btn.setEnabled(has_row or has_items)
    page.selector_move_up_btn.setEnabled(single_selected and current_row > 0)
    page.selector_move_down_btn.setEnabled(single_selected and current_row < page.selector_assignment_list.count() - 1)
    page.selector_comment_btn.setEnabled(single_selected)
    page.selector_delete_comment_btn.setVisible(has_comment)
    page.selector_delete_comment_btn.setEnabled(has_comment)


def sync_selector_card_selection_states(page) -> None:
    if not hasattr(page, "selector_assignment_list"):
        return
    for row in range(page.selector_assignment_list.count()):
        item = page.selector_assignment_list.item(row)
        widget = page.selector_assignment_list.itemWidget(item)
        if isinstance(widget, MiniAssignmentCard):
            widget.set_selected(item.isSelected())
            continue
        card = widget.findChild(MiniAssignmentCard) if widget is not None else None
        if isinstance(card, MiniAssignmentCard):
            card.set_selected(item.isSelected())


def sync_selector_assignment_order(page) -> None:
    if not hasattr(page, "selector_assignment_list"):
        return
    ordered: list[dict] = []
    for row in range(page.selector_assignment_list.count()):
        item = page.selector_assignment_list.item(row)
        assignment = item.data(Qt.UserRole)
        normalized = page._normalize_selector_tool(assignment)
        if normalized is not None:
            ordered.append(normalized)
    page._selector_assigned_tools = ordered
    page._refresh_selector_assignment_rows()
    update_selector_assignment_buttons(page)


def on_selector_tools_dropped(page, dropped_items: list, insert_row: int) -> None:
    updated, selected_row = page._selector_assignment_state.apply_dropped_tools(
        page._selector_assigned_tools,
        dropped_items,
        insert_row,
    )
    if selected_row is None:
        return
    page._selector_assigned_tools = updated
    page._rebuild_selector_assignment_list()
    page.selector_assignment_list.setCurrentRow(selected_row)


def remove_selector_assignment(page) -> None:
    rows = page._selector_selected_rows()
    if not rows:
        return
    for row in reversed(rows):
        if 0 <= row < len(page._selector_assigned_tools):
            page._selector_assigned_tools.pop(row)
    page._rebuild_selector_assignment_list()
    if page.selector_assignment_list.count() > 0:
        page.selector_assignment_list.setCurrentRow(min(rows[0], page.selector_assignment_list.count() - 1))


def remove_selector_assignments_by_keys(page, tool_keys: list[tuple[str, str | None]]) -> None:
    remaining = page._selector_assignment_state.remove_assignments_by_keys(
        page._selector_assigned_tools,
        tool_keys,
    )
    if len(remaining) == len(page._selector_assigned_tools):
        return
    page._selector_assigned_tools = remaining
    page._rebuild_selector_assignment_list()


def move_selector_up(page) -> None:
    selected_rows = page._selector_selected_rows()
    if len(selected_rows) != 1:
        return
    row = selected_rows[0]
    if row <= 0 or row >= len(page._selector_assigned_tools):
        return
    page._selector_assigned_tools[row - 1], page._selector_assigned_tools[row] = (
        page._selector_assigned_tools[row],
        page._selector_assigned_tools[row - 1],
    )
    page._rebuild_selector_assignment_list()
    page.selector_assignment_list.setCurrentRow(row - 1)


def move_selector_down(page) -> None:
    selected_rows = page._selector_selected_rows()
    if len(selected_rows) != 1:
        return
    row = selected_rows[0]
    if row < 0 or row >= len(page._selector_assigned_tools) - 1:
        return
    page._selector_assigned_tools[row], page._selector_assigned_tools[row + 1] = (
        page._selector_assigned_tools[row + 1],
        page._selector_assigned_tools[row],
    )
    page._rebuild_selector_assignment_list()
    page.selector_assignment_list.setCurrentRow(row + 1)


def add_selector_comment(page) -> None:
    selected_rows = page._selector_selected_rows()
    if len(selected_rows) != 1:
        return
    row = selected_rows[0]
    if row < 0 or row >= len(page._selector_assigned_tools):
        return
    current = str(page._selector_assigned_tools[row].get("comment") or "").strip()
    text, ok = QInputDialog.getText(
        page,
        page._t("tool_library.selector.add_comment", "Add Comment"),
        page._t("tool_library.selector.comment_prompt", "Comment:"),
        text=current,
    )
    if ok:
        page._selector_assigned_tools[row]["comment"] = text.strip()
        page._rebuild_selector_assignment_list()
        page.selector_assignment_list.setCurrentRow(row)


def delete_selector_comment(page) -> None:
    selected_rows = page._selector_selected_rows()
    if len(selected_rows) != 1:
        return
    row = selected_rows[0]
    if row < 0 or row >= len(page._selector_assigned_tools):
        return
    page._selector_assigned_tools[row].pop("comment", None)
    page._rebuild_selector_assignment_list()
    page.selector_assignment_list.setCurrentRow(row)


def on_selector_cancel(page) -> None:
    main_win = page.window()
    if hasattr(main_win, "_clear_selector_session"):
        main_win._clear_selector_session()
    if hasattr(main_win, "_back_to_setup_manager"):
        main_win._back_to_setup_manager()


def on_selector_done(page) -> None:
    main_win = page.window()
    if hasattr(main_win, "_send_selector_selection"):
        main_win._send_selector_selection()


def on_selector_toggle_clicked(page) -> None:
    if not page._selector_active:
        return
    if page.selector_toggle_btn.isChecked():
        page._set_selector_panel_mode("selector")
    else:
        page._set_selector_panel_mode("details")

