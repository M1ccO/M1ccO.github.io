"""Batch and group edit action helpers for FixturePage."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QMessageBox

from shared.data.backup_helpers import create_db_backup
from ui.fixture_editor_dialog import AddEditFixtureDialog


def _backup(page, tag: str) -> Path:
    return create_db_backup(Path(page.fixture_service.db.path), tag)


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


def batch_edit_fixtures(page, fixture_ids: list[str]) -> None:
    saved_before: list[dict] = []
    total = len(fixture_ids)
    for idx, fixture_id in enumerate(fixture_ids, 1):
        fixture = page.fixture_service.get_fixture(fixture_id)
        if not fixture:
            continue
        dlg = AddEditFixtureDialog(
            page,
            fixture=fixture,
            translate=page._t,
            batch_label=f"{idx}/{total}",
        )
        if dlg.exec() != QDialog.Accepted:
            if saved_before:
                action = prompt_batch_cancel_behavior(page)
                if action == 'undo':
                    for previous in reversed(saved_before):
                        page.fixture_service.save_fixture(previous)
            page.refresh_list()
            return
        saved_before.append(dict(fixture))
        page.fixture_service.save_fixture(dlg.get_fixture_data())
    page.refresh_list()


def group_edit_fixtures(page, fixture_ids: list[str]) -> None:
    dlg = AddEditFixtureDialog(
        page,
        translate=page._t,
        group_edit_mode=True,
        group_count=len(fixture_ids),
    )
    baseline = dlg.get_fixture_data()
    if dlg.exec() != QDialog.Accepted:
        return
    edited_data = dlg.get_fixture_data()
    changed_fields = {
        key: value
        for key, value in edited_data.items()
        if value != baseline.get(key)
    }
    changed_fields.pop('fixture_id', None)
    if not changed_fields:
        QMessageBox.information(
            page,
            page._t('jaw_library.group_edit.no_changes_title', 'No changes'),
            page._t('jaw_library.group_edit.no_changes_body', 'No fields were changed.'),
        )
        return

    _backup(page, 'group_edit')
    for fixture_id in fixture_ids:
        fixture = page.fixture_service.get_fixture(fixture_id)
        if not fixture:
            continue
        updated = dict(fixture)
        updated.update(changed_fields)
        updated['fixture_id'] = fixture_id
        page.fixture_service.save_fixture(updated)
    page.refresh_list()


__all__ = [
    "batch_edit_fixtures",
    "group_edit_fixtures",
    "prompt_batch_cancel_behavior",
]


