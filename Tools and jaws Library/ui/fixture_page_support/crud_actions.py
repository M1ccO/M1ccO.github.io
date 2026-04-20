"""CRUD action handlers for FixturePage.

Extracted from fixture_page.py (Phase 5 Pass 8) to reduce page size.
All public functions take the page object as their first argument.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from shared.ui.helpers.editor_helpers import (
    apply_secondary_button_theme,
    ask_multi_edit_mode,
    create_dialog_buttons,
    setup_editor_dialog,
)
from ui.fixture_editor_dialog import AddEditFixtureDialog

__all__ = [
    "add_fixture",
    "copy_fixture",
    "delete_fixture",
    "edit_fixture",
    "prompt_text",
    "save_from_dialog",
]


def save_from_dialog(page, dlg, original_fixture_id: str | None = None) -> None:
    try:
        data = dlg.get_fixture_data()
        page.fixture_service.save_fixture(data)
        new_fixture_id = data['fixture_id']
        if original_fixture_id and original_fixture_id != new_fixture_id:
            page.fixture_service.delete_fixture(original_fixture_id)
        page.current_fixture_id = new_fixture_id
        page._current_item_id = new_fixture_id
        page.refresh_list()
        page.populate_details(page.fixture_service.get_fixture(new_fixture_id))
    except ValueError as exc:
        QMessageBox.warning(page, page._t('tool_library.error.invalid_data', 'Invalid data'), str(exc))


def add_fixture(page) -> None:
    dlg = AddEditFixtureDialog(page, translate=page._t)
    if dlg.exec() == QDialog.Accepted:
        save_from_dialog(page, dlg)


def edit_fixture(page) -> None:
    selected_ids = page._selected_fixture_ids()
    if not selected_ids:
        QMessageBox.information(
            page,
            page._t('fixture_library.action.edit_fixture', 'Edit fixture'),
            page._t('fixture_library.message.select_fixture_first', 'Select a fixture first.'),
        )
        return
    if len(selected_ids) > 1:
        mode = ask_multi_edit_mode(page, len(selected_ids), page._t)
        if mode == 'batch':
            page._batch_edit_fixtures(selected_ids)
        elif mode == 'group':
            page._group_edit_fixtures(selected_ids)
        return
    fixture = page.fixture_service.get_fixture(selected_ids[0])
    dlg = AddEditFixtureDialog(page, fixture=fixture, translate=page._t)
    if dlg.exec() == QDialog.Accepted:
        save_from_dialog(page, dlg, original_fixture_id=fixture.get('fixture_id', ''))


def delete_fixture(page) -> None:
    if not page.current_fixture_id:
        QMessageBox.information(
            page,
            page._t('fixture_library.action.delete_fixture', 'Delete fixture'),
            page._t('fixture_library.message.select_fixture_first', 'Select a fixture first.'),
        )
        return

    box = QMessageBox(page)
    setup_editor_dialog(box)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle(page._t('fixture_library.action.delete_fixture', 'Delete fixture'))
    box.setText(
        page._t(
            'fixture_library.message.delete_fixture_prompt',
            'Delete fixture {fixture_id}?',
            fixture_id=page.current_fixture_id,
        )
    )
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

    yes_btn = box.button(QMessageBox.Yes)
    no_btn = box.button(QMessageBox.No)
    if yes_btn is not None:
        yes_btn.setText(page._t('common.yes', 'Yes'))
        yes_btn.setProperty('panelActionButton', True)
        yes_btn.setProperty('dangerAction', True)
    if no_btn is not None:
        no_btn.setText(page._t('common.no', 'No'))
        no_btn.setProperty('panelActionButton', True)
        no_btn.setProperty('secondaryAction', True)

    if box.exec() != QMessageBox.Yes:
        return

    deleted_id = page.current_fixture_id
    page.fixture_service.delete_fixture(deleted_id)
    page.item_deleted.emit(deleted_id)
    page.current_fixture_id = None
    page._current_item_id = None
    page.refresh_list()
    page.populate_details(None)


def copy_fixture(page) -> None:
    if not page.current_fixture_id:
        QMessageBox.information(
            page,
            page._t('fixture_library.action.copy_fixture', 'Copy fixture'),
            page._t('fixture_library.message.select_fixture_first', 'Select a fixture first.'),
        )
        return
    fixture = page.fixture_service.get_fixture(page.current_fixture_id)
    if not fixture:
        return

    new_id, accepted = prompt_text(
        page,
        page._t('fixture_library.action.copy_fixture', 'Copy fixture'),
        page._t('fixture_library.prompt.new_fixture_id', 'New Fixture ID:'),
    )
    if not accepted or not new_id.strip():
        return

    copied = dict(fixture)
    copied['fixture_id'] = new_id.strip()
    try:
        page.fixture_service.save_fixture(copied)
        page.current_fixture_id = copied['fixture_id']
        page._current_item_id = copied['fixture_id']
        page.refresh_list()
        page.populate_details(page.fixture_service.get_fixture(page.current_fixture_id))
    except ValueError as exc:
        QMessageBox.warning(page, page._t('fixture_library.action.copy_fixture', 'Copy fixture'), str(exc))


def prompt_text(page, title: str, label: str, initial: str = '') -> tuple[str, bool]:
    dlg = QDialog(page)
    setup_editor_dialog(dlg)
    dlg.setWindowTitle(title)
    dlg.setModal(True)

    root = QVBoxLayout(dlg)
    root.setContentsMargins(12, 12, 12, 12)
    root.setSpacing(8)

    prompt_label = QLabel(label)
    prompt_label.setProperty('detailFieldKey', True)
    prompt_label.setWordWrap(True)
    root.addWidget(prompt_label)

    editor = QLineEdit()
    editor.setText(initial)
    root.addWidget(editor)

    buttons = create_dialog_buttons(
        dlg,
        save_text=page._t('common.ok', 'OK'),
        cancel_text=page._t('common.cancel', 'Cancel'),
        on_save=dlg.accept,
        on_cancel=dlg.reject,
    )
    root.addWidget(buttons)

    apply_secondary_button_theme(dlg, buttons.button(QDialogButtonBox.Save))
    editor.setFocus()
    editor.selectAll()
    accepted = dlg.exec() == QDialog.Accepted
    return editor.text(), accepted

