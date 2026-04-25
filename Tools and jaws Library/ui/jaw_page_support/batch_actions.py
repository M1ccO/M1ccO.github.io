"""Batch and group edit action helpers for JawPage."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QMessageBox

from shared.data.backup_helpers import create_db_backup
from shared.ui.transition_shell import cancel_receiver_ready_signal
from shared.ui.main_window_helpers import exec_dialog_with_blur
from ui.jaw_editor_dialog import AddEditJawDialog


def _editor_parent(page):
    host_window_getter = getattr(page, 'window', None)
    if callable(host_window_getter):
        try:
            host_window = host_window_getter()
            if host_window is not None:
                return host_window
        except Exception:
            pass
    return page


def _prepare_modal_host_window(page):
    host = _editor_parent(page)

    pending_receiver_signal = getattr(host, '_pending_receiver_ready_signal', None)
    pending_receiver_callback = getattr(pending_receiver_signal, 'callback', None)
    cancel_receiver_ready_signal(host)
    if callable(pending_receiver_callback):
        try:
            pending_receiver_callback()
        except Exception:
            pass

    pending_fade_timer = getattr(host, '_pending_fade_in_timer', None)
    if pending_fade_timer is not None:
        try:
            pending_fade_timer.stop()
        except Exception:
            pass
        try:
            host._pending_fade_in_timer = None
        except Exception:
            pass

    fade_anim = getattr(host, '_fade_anim', None)
    if fade_anim is not None:
        try:
            fade_anim.stop()
        except Exception:
            pass
        try:
            host._fade_anim = None
        except Exception:
            pass

    try:
        host.setWindowOpacity(1.0)
    except Exception:
        pass

    return host


def _backup(page, tag: str) -> Path:
    return create_db_backup(Path(page.jaw_service.db.path), tag)


def prompt_batch_cancel_behavior(page) -> str:
    box = QMessageBox(page)
    box.setIcon(QMessageBox.Question)
    box.setWindowTitle(page._t('jaw_library.batch.cancel.title', 'Batch edit cancelled'))
    box.setText(
        page._t(
            'jaw_library.batch.cancel.body',
            "You stopped editing partway through the batch. Do you want to keep the changes you've already saved, or undo all of them?",
        )
    )
    keep_btn = box.addButton(
        page._t('jaw_library.batch.cancel.keep', 'Keep'),
        QMessageBox.AcceptRole,
    )
    undo_btn = box.addButton(
        page._t('jaw_library.batch.cancel.undo', 'Undo'),
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


def batch_edit_jaws(page, jaw_ids: list[str]) -> None:
    parent = _prepare_modal_host_window(page)
    saved_before: list[dict] = []
    total = len(jaw_ids)
    for idx, jaw_id in enumerate(jaw_ids, 1):
        jaw = page.jaw_service.get_jaw(jaw_id)
        if not jaw:
            continue
        dlg = AddEditJawDialog(
            parent=parent,
            jaw=jaw,
            translate=page._t,
            batch_label=f"{idx}/{total}",
        )
        if dlg.exec() != QDialog.Accepted:
            if saved_before:
                action = prompt_batch_cancel_behavior(page)
                if action == 'undo':
                    for previous in reversed(saved_before):
                        page.jaw_service.save_jaw(previous)
            page.refresh_catalog()
            return
        saved_before.append(dict(jaw))
        page.jaw_service.save_jaw(
            dlg.get_accepted_jaw_data() if hasattr(dlg, 'get_accepted_jaw_data') else dlg.get_jaw_data()
        )
    page.refresh_catalog()


def group_edit_jaws(page, jaw_ids: list[str]) -> None:
    parent = _prepare_modal_host_window(page)
    dlg = AddEditJawDialog(
        parent=parent,
        translate=page._t,
        group_edit_mode=True,
        group_count=len(jaw_ids),
    )
    baseline = dlg.get_jaw_data()
    if dlg.exec() != QDialog.Accepted:
        return
    edited_data = dlg.get_accepted_jaw_data() if hasattr(dlg, 'get_accepted_jaw_data') else dlg.get_jaw_data()
    changed_fields = {
        key: value
        for key, value in edited_data.items()
        if value != baseline.get(key)
    }
    changed_fields.pop('jaw_id', None)
    if not changed_fields:
        QMessageBox.information(
            page,
            page._t('jaw_library.group_edit.no_changes_title', 'No changes'),
            page._t('jaw_library.group_edit.no_changes_body', 'No fields were changed.'),
        )
        return

    _backup(page, 'group_edit')
    for jaw_id in jaw_ids:
        jaw = page.jaw_service.get_jaw(jaw_id)
        if not jaw:
            continue
        updated = dict(jaw)
        updated.update(changed_fields)
        updated['jaw_id'] = jaw_id
        page.jaw_service.save_jaw(updated)
    page.refresh_catalog()


__all__ = [
    "batch_edit_jaws",
    "group_edit_jaws",
    "prompt_batch_cancel_behavior",
]
