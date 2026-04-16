"""Batch and group edit action helpers for SetupPage."""

from __future__ import annotations

from pathlib import Path
import traceback

from PySide6.QtWidgets import QDialog, QMessageBox

from shared.data.backup_helpers import create_db_backup, prune_backups
from ui.work_editor_dialog import WorkEditorDialog
from ui.setup_page_support.work_editor_launch import exec_work_editor_dialog, resolve_work_editor_parent


def _backup(page, tag: str) -> Path:
    return create_db_backup(Path(page.work_service.db.path), tag)


def prompt_batch_cancel_behavior(page) -> str:
    box = QMessageBox(page)
    box.setIcon(QMessageBox.Question)
    box.setWindowTitle(page._t("setup_page.batch.cancel.title", "Batch edit cancelled"))
    box.setText(
        page._t(
            "setup_page.batch.cancel.body",
            "You stopped editing partway through the batch. Do you want to keep the changes you've already saved, or undo all of them?",
        )
    )
    keep_btn = box.addButton(
        page._t("setup_page.batch.cancel.keep", "Keep"),
        QMessageBox.AcceptRole,
    )
    undo_btn = box.addButton(
        page._t("setup_page.batch.cancel.undo", "Undo"),
        QMessageBox.DestructiveRole,
    )
    box.addButton(page._t("common.cancel", "Cancel"), QMessageBox.RejectRole)
    box.exec()
    clicked = box.clickedButton()
    if clicked is undo_btn:
        return "undo"
    if clicked is keep_btn:
        return "keep"
    return "keep"


def batch_edit_works(page, work_ids: list[str]) -> None:
    saved_before: list[dict] = []
    total = len(work_ids)
    host_window = resolve_work_editor_parent(page)
    for idx, work_id in enumerate(work_ids, 1):
        work = page.work_service.get_work(work_id)
        if not work:
            continue
        try:
            dialog = WorkEditorDialog(
                page.draw_service,
                work=work,
                parent=None,
                style_host=host_window,
                translate=page._t,
                batch_label=f"{idx}/{total}",
                drawings_enabled=page.drawings_enabled,
                machine_profile_key=page.work_service.get_machine_profile_key(),
            )
        except Exception as exc:
            QMessageBox.critical(
                page,
                page._t("setup_page.message.open_editor_failed", "Work Editor failed to open"),
                f"{exc}\n\n{traceback.format_exc()}",
            )
            page.refresh_works()
            return
        if exec_work_editor_dialog(dialog) != QDialog.Accepted:
            if saved_before:
                action = prompt_batch_cancel_behavior(page)
                if action == "undo":
                    for previous in reversed(saved_before):
                        page.work_service.save_work(previous)
            page.refresh_works()
            return
        saved_before.append(dict(work))
        page.work_service.save_work(dialog.get_work_data())
    page.refresh_works()


def group_edit_works(page, work_ids: list[str]) -> None:
    host_window = resolve_work_editor_parent(page)
    try:
        baseline_dialog = WorkEditorDialog(
            page.draw_service,
            parent=None,
            style_host=host_window,
            translate=page._t,
            group_edit_mode=True,
            group_count=len(work_ids),
            drawings_enabled=page.drawings_enabled,
            machine_profile_key=page.work_service.get_machine_profile_key(),
        )
    except Exception as exc:
        QMessageBox.critical(
            page,
            page._t("setup_page.message.open_editor_failed", "Work Editor failed to open"),
            f"{exc}\n\n{traceback.format_exc()}",
        )
        page.refresh_works()
        return
    baseline = baseline_dialog.get_work_data()
    if exec_work_editor_dialog(baseline_dialog) != QDialog.Accepted:
        return
    edited_data = baseline_dialog.get_work_data()
    changed_fields = {
        key: value
        for key, value in edited_data.items()
        if value != baseline.get(key)
    }
    changed_fields.pop("work_id", None)
    if not changed_fields:
        QMessageBox.information(
            page,
            page._t("setup_page.group_edit.no_changes_title", "No changes"),
            page._t("setup_page.group_edit.no_changes_body", "No fields were changed."),
        )
        return

    _backup(page, "group_edit")
    for work_id in work_ids:
        work = page.work_service.get_work(work_id)
        if not work:
            continue
        updated = dict(work)
        updated.update(changed_fields)
        updated["work_id"] = work_id
        page.work_service.save_work(updated)
    page.refresh_works()


__all__ = [
    "batch_edit_works",
    "group_edit_works",
    "prompt_batch_cancel_behavior",
]
