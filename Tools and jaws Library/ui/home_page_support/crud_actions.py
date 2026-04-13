"""CRUD action handlers for HomePage.

Extracted from home_page.py (Phase 10 Pass 2).
All public functions take the page object as their first argument.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QMessageBox

from ui.tool_editor_dialog import AddEditToolDialog

__all__ = ["add_tool", "copy_tool", "delete_tool", "edit_tool"]


def add_tool(page) -> None:
    """Open AddEditToolDialog in 'add' mode."""
    dlg = AddEditToolDialog(
        parent=page,
        tool=None,
        tool_service=page.tool_service,
        translate=page._t,
    )
    if dlg.exec() == QDialog.Accepted:
        page.refresh_list()


def edit_tool(page) -> None:
    """Open AddEditToolDialog in 'edit' mode for selected tool."""
    tool = page._get_selected_tool()
    if not tool:
        QMessageBox.information(
            page,
            page._t('tool_library.message.edit_tool', 'Edit tool'),
            page._t('tool_library.message.select_tool_first', 'Select a tool first.'),
        )
        return

    uid = tool.get('uid')
    dlg = AddEditToolDialog(
        parent=page,
        tool=tool,
        tool_service=page.tool_service,
        translate=page._t,
    )
    if dlg.exec() == QDialog.Accepted:
        page.refresh_list()
        if uid:
            page._restore_selection_by_uid(uid)


def delete_tool(page) -> None:
    """Delete selected tool(s) with confirmation."""
    uids = page._selected_tool_uids()
    if not uids:
        QMessageBox.information(
            page,
            page._t('tool_library.message.delete_tool', 'Delete tool'),
            page._t('tool_library.message.select_tool_first', 'Select a tool first.'),
        )
        return

    count = len(uids)
    reply = QMessageBox.question(
        page,
        page._t('tool_library.message.confirm_delete', 'Confirm Delete'),
        page._t('tool_library.message.delete_count', 'Delete {count} tool(s)?', count=count),
    )
    if reply != QMessageBox.Yes:
        return

    for uid in uids:
        tool = page.tool_service.get_tool_by_uid(uid)
        if tool:
            tool_id = tool.get('id', '')
            page.tool_service.delete_tool(tool_id)
            page.item_deleted.emit(tool_id)

    page.refresh_list()


def copy_tool(page) -> None:
    """Copy selected tool as a new tool."""
    tool = page._get_selected_tool()
    if not tool:
        QMessageBox.information(
            page,
            page._t('tool_library.message.copy_tool', 'Copy tool'),
            page._t('tool_library.message.select_tool_first', 'Select a tool first.'),
        )
        return

    tool_copy = dict(tool)
    tool_copy['id'] = ''  # Clear ID so dialog treats it as new
    dlg = AddEditToolDialog(
        parent=page,
        tool=tool_copy,
        tool_service=page.tool_service,
        translate=page._t,
    )
    if dlg.exec() == QDialog.Accepted:
        page.refresh_list()
