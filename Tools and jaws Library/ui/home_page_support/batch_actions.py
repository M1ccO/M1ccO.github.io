"""Batch and group edit action helpers for HomePage (Tool Library)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QMessageBox

from shared.data.backup_helpers import create_db_backup
from ui.tool_editor_dialog import AddEditToolDialog


def _backup(page, tag: str) -> Path:
    return create_db_backup(Path(page.tool_service.db.path), tag)


def prompt_batch_cancel_behavior(page) -> str:
    box = QMessageBox(page)
    box.setIcon(QMessageBox.Question)
    box.setWindowTitle(page._t('tool_library.batch.cancel.title', 'Batch edit cancelled'))
    box.setText(
        page._t(
            'tool_library.batch.cancel.body',
            'You stopped editing partway through the batch. Do you want to keep the changes you\'ve already saved, or undo all of them?',
        )
    )
    keep_btn = box.addButton(
        page._t('tool_library.batch.cancel.keep', 'Keep'),
        QMessageBox.AcceptRole,
    )
    undo_btn = box.addButton(
        page._t('tool_library.batch.cancel.undo', 'Undo'),
        QMessageBox.DestructiveRole,
    )
    box.addButton(page._t('common.cancel', 'Cancel'), QMessageBox.RejectRole)
    box.exec()
    clicked = box.clickedButton()
    if clicked is undo_btn:
        return 'undo'
    if clicked is keep_btn:
        return 'keep'
    return 'keep'


def batch_edit_tools(page, uids: list[int]) -> None:
    saved_before: list[dict] = []
    total = len(uids)
    for idx, uid in enumerate(uids, 1):
        tool = page.tool_service.get_tool_by_uid(uid)
        if not tool:
            continue
        draft_tool = dict(tool)
        while True:
            dlg = AddEditToolDialog(
                page,
                tool=draft_tool,
                tool_service=page.tool_service,
                translate=page._t,
                batch_label=f"{idx}/{total}",
            )
            if dlg.exec() != QDialog.Accepted:
                if saved_before:
                    action = prompt_batch_cancel_behavior(page)
                    if action == 'undo':
                        for previous in reversed(saved_before):
                            page.tool_service.save_tool(previous, allow_duplicate=True)
                page.refresh_list()
                return
            result = page._save_from_dialog(dlg)
            if result == 'saved':
                saved_before.append(tool)
                break
            if result == 'retry':
                draft_tool = dlg.get_tool_data()
                draft_tool['uid'] = uid
                continue
            page.refresh_list()
            return
    page.refresh_list()


def group_edit_tools(page, uids: list[int]) -> None:
    dlg = AddEditToolDialog(
        page,
        tool_service=page.tool_service,
        translate=page._t,
        group_edit_mode=True,
        group_count=len(uids),
    )
    baseline = dlg.get_tool_data()
    if dlg.exec() != QDialog.Accepted:
        return
    edited_data = dlg.get_tool_data()
    changed_fields = {
        key: value
        for key, value in edited_data.items()
        if value != baseline.get(key)
    }
    if not changed_fields:
        QMessageBox.information(
            page,
            page._t('tool_library.group_edit.no_changes_title', 'No changes'),
            page._t('tool_library.group_edit.no_changes_body', 'No fields were changed.'),
        )
        return

    _backup(page, 'group_edit')
    for uid in uids:
        existing = page.tool_service.get_tool_by_uid(uid)
        if not existing:
            continue
        merged = dict(existing)
        merged.update(changed_fields)
        merged['uid'] = uid
        page.tool_service.save_tool(merged, allow_duplicate=True)
    page.refresh_list()


__all__ = [
    "batch_edit_tools",
    "group_edit_tools",
    "prompt_batch_cancel_behavior",
]
