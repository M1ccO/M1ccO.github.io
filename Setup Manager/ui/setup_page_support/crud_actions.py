from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QInputDialog, QMessageBox

from shared.data.backup_helpers import create_db_backup
from ui.work_editor_dialog import WorkEditorDialog
from ui.setup_page_support.crud_dialogs import ask_delete_logbook_entries, confirm_delete_work

try:
    from shared.ui.helpers.editor_helpers import ask_multi_edit_mode
except ModuleNotFoundError:
    from editor_helpers import ask_multi_edit_mode


def create_work(page) -> None:
    dialog = WorkEditorDialog(
        page.draw_service,
        parent=page,
        translate=page._t,
        drawings_enabled=page.drawings_enabled,
    )
    if dialog.exec() != QDialog.Accepted:
        return
    try:
        page.work_service.save_work(dialog.get_work_data())
        page.refresh_works()
    except Exception as exc:
        QMessageBox.critical(page, page._t("setup_page.message.save_failed", "Save failed"), str(exc))


def edit_work(page) -> None:
    selected_ids = page._selected_work_ids()
    if not selected_ids:
        return
    if len(selected_ids) > 1:
        # Multi-select path intentionally requires an explicit edit strategy so
        # batch and group edits remain user-driven and predictable.
        mode = ask_multi_edit_mode(page, len(selected_ids), page._t)
        if mode == "batch":
            page._batch_edit_works(selected_ids)
        elif mode == "group":
            page._group_edit_works(selected_ids)
        return

    work_id = selected_ids[0]
    work = page.work_service.get_work(work_id)
    if not work:
        QMessageBox.warning(
            page,
            page._t("setup_page.message.missing_title", "Missing"),
            page._t("setup_page.message.work_no_longer_exists", "Work no longer exists."),
        )
        page.refresh_works()
        return

    dialog = WorkEditorDialog(
        page.draw_service,
        work=work,
        parent=page,
        translate=page._t,
        drawings_enabled=page.drawings_enabled,
    )
    if dialog.exec() != QDialog.Accepted:
        return
    try:
        page.work_service.save_work(dialog.get_work_data())
        page.refresh_works()
    except Exception as exc:
        QMessageBox.critical(page, page._t("setup_page.message.save_failed", "Save failed"), str(exc))


def delete_work(page) -> None:
    work_id = page._selected_work_id()
    if not work_id:
        return

    logbook_count = page.logbook_service.count_entries_for_work(work_id)

    # Always take a backup before any destructive action so work deletion remains reversible.
    try:
        create_db_backup(Path(page.work_service.db.path), "work_delete")
    except Exception as exc:
        QMessageBox.critical(
            page,
            page._t("setup_page.message.backup_failed_title", "Backup failed"),
            page._t(
                "setup_page.message.backup_failed_body",
                "Could not create a backup before deleting:\n{error}",
                error=str(exc),
            ),
        )
        return

    if not confirm_delete_work(page, work_id):
        return

    delete_logbook = False
    if logbook_count > 0:
        # Preserve existing behavior: users choose whether historical run entries
        # are retained or removed with the work.
        decision = ask_delete_logbook_entries(page, work_id, logbook_count)
        if decision is None:
            return
        delete_logbook = decision

    page.work_service.delete_work(work_id)
    if delete_logbook:
        page.logbook_service.delete_entries_for_work(work_id)
    page.refresh_works()


def duplicate_work(page) -> None:
    work_id = page._selected_work_id()
    if not work_id:
        return

    new_id, ok = QInputDialog.getText(
        page,
        page._t("setup_page.message.duplicate_work_title", "Duplicate work"),
        page._t("setup_page.message.new_work_id", "New work ID"),
    )
    # New work ID is mandatory; description stays optional for fast copy workflows.
    if not ok or not (new_id or "").strip():
        return

    desc, _ = QInputDialog.getText(
        page,
        page._t("setup_page.field.description", "Description"),
        page._t("setup_page.message.new_description_optional", "New description (optional)"),
    )
    try:
        page.work_service.duplicate_work(work_id, new_id.strip(), desc.strip())
        page.refresh_works()
    except Exception as exc:
        QMessageBox.critical(
            page,
            page._t("setup_page.message.duplicate_failed", "Duplicate failed"),
            str(exc),
        )
