from __future__ import annotations

from pathlib import Path
import traceback

from PySide6.QtWidgets import QDialog, QInputDialog, QMessageBox

from shared.data.backup_helpers import create_db_backup
from ui.work_editor_factory import create_work_editor_dialog
from ui.setup_page_support.crud_dialogs import ask_delete_logbook_entries, confirm_delete_work
from ui.setup_page_support.work_editor_launch import (
    exec_work_editor_dialog,
    pause_preload_before_work_editor_launch,
    prime_work_editor_dialog,
    resume_preload_after_work_editor_launch,
    resolve_work_editor_parent,
)

try:
    from shared.ui.helpers.editor_helpers import ask_multi_edit_mode
except ModuleNotFoundError:
    from editor_helpers import ask_multi_edit_mode


def _dialog_cache(page) -> dict:
    cache = getattr(page, "_work_editor_dialog_cache", None)
    if isinstance(cache, dict):
        return cache
    cache = {}
    page._work_editor_dialog_cache = cache
    return cache


def _create_work_editor_dialog(page, host_window, work=None):
    # Parent to host_window so Qt's QDialog first-show adjustPosition centers
    # on the visible host instead of screen default. Without a parent, Qt
    # ignored pre-show move(-32000) and briefly flashed the native titlebar
    # at its default screen position before our final geometry applied.
    return create_work_editor_dialog(
        page.draw_service,
        work=work,
        parent=host_window,
        style_host=host_window,
        translate=page._t,
        drawings_enabled=page.drawings_enabled,
        machine_profile_key=page.work_service.get_machine_profile_key(),
    )


def _get_or_create_shared_dialog(page, host_window):
    cache = _dialog_cache(page)
    dialog = cache.get("shared")
    if dialog is not None:
        return dialog
    dialog = _create_work_editor_dialog(page, host_window, work=None)
    prime_work_editor_dialog(dialog)
    cache["shared"] = dialog
    return dialog


def _prepare_shared_dialog_context(dialog, work_payload: dict | None) -> None:
    payload = dict(work_payload or {})
    dialog.work = payload
    dialog.is_edit = bool(payload)

    # Reset selector session state left over from any previous use of this
    # shared dialog.  The controller owns all selector state and delegates
    # to SelectorSessionCoordinator for lifecycle tracking.
    ctrl = getattr(dialog, "_selector_ctrl", None)
    if ctrl is not None:
        ctrl.reset_for_reuse()

    try:
        dialog.setWindowTitle(dialog._dialog_title())
    except Exception:
        pass
    try:
        populate = getattr(dialog, "_payload_adapter", None)
        if populate is not None and hasattr(populate, "populate_dialog"):
            populate.populate_dialog(dialog, payload)
        else:
            load_work = getattr(dialog, "_load_work", None)
            if callable(load_work):
                load_work()
    except Exception:
        pass
    try:
        ensure_surface = getattr(dialog, "_ensure_normal_editor_surface_visible", None)
        if callable(ensure_surface):
            ensure_surface()
        ensure_content = getattr(dialog, "_ensure_normal_editor_content_visible", None)
        if callable(ensure_content):
            ensure_content()
    except Exception:
        pass


def create_work(page) -> None:
    host_window = resolve_work_editor_parent(page)
    preload_paused = pause_preload_before_work_editor_launch(host_window)
    try:
        dialog = _get_or_create_shared_dialog(page, host_window)
        _prepare_shared_dialog_context(dialog, None)
        prime_work_editor_dialog(dialog)
    except Exception as exc:
        if preload_paused:
            resume_preload_after_work_editor_launch(host_window)
        QMessageBox.critical(
            page,
            page._t("setup_page.message.open_editor_failed", "Work Editor failed to open"),
            f"{exc}\n\n{traceback.format_exc()}",
        )
        return
    try:
        if exec_work_editor_dialog(dialog) != QDialog.Accepted:
            return
        try:
            page.work_service.save_work(dialog.get_work_data())
            page.refresh_works()
        except Exception as exc:
            QMessageBox.critical(page, page._t("setup_page.message.save_failed", "Save failed"), str(exc))
    finally:
        if preload_paused:
            resume_preload_after_work_editor_launch(host_window)


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

    host_window = resolve_work_editor_parent(page)
    preload_paused = pause_preload_before_work_editor_launch(host_window)
    try:
        dialog = _get_or_create_shared_dialog(page, host_window)
        _prepare_shared_dialog_context(dialog, work)
        prime_work_editor_dialog(dialog)
    except Exception as exc:
        if preload_paused:
            resume_preload_after_work_editor_launch(host_window)
        QMessageBox.critical(
            page,
            page._t("setup_page.message.open_editor_failed", "Work Editor failed to open"),
            f"{exc}\n\n{traceback.format_exc()}",
        )
        return
    try:
        if exec_work_editor_dialog(dialog) != QDialog.Accepted:
            return
        try:
            page.work_service.save_work(dialog.get_work_data())
            page.refresh_works()
        except Exception as exc:
            QMessageBox.critical(page, page._t("setup_page.message.save_failed", "Save failed"), str(exc))
    finally:
        if preload_paused:
            resume_preload_after_work_editor_launch(host_window)


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
