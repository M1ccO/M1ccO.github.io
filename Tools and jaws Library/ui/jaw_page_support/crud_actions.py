"""CRUD action handlers for JawPage.

Extracted from jaw_page.py (Phase 5 Pass 8) to reduce page size.
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
from ui.jaw_editor_dialog import AddEditJawDialog

__all__ = [
    "add_jaw",
    "copy_jaw",
    "delete_jaw",
    "edit_jaw",
    "prompt_text",
    "save_from_dialog",
]


def save_from_dialog(page, dlg, original_jaw_id: str | None = None) -> None:
    try:
        data = dlg.get_jaw_data()
        page.jaw_service.save_jaw(data)
        new_jaw_id = data['jaw_id']
        if original_jaw_id and original_jaw_id != new_jaw_id:
            page.jaw_service.delete_jaw(original_jaw_id)
        page.current_jaw_id = new_jaw_id
        page._current_item_id = new_jaw_id
        page.refresh_list()
        page.populate_details(page.jaw_service.get_jaw(new_jaw_id))
    except ValueError as exc:
        QMessageBox.warning(page, page._t('tool_library.error.invalid_data', 'Invalid data'), str(exc))


def add_jaw(page) -> None:
    dlg = AddEditJawDialog(page, translate=page._t)
    if dlg.exec() == QDialog.Accepted:
        save_from_dialog(page, dlg)


def edit_jaw(page) -> None:
    selected_ids = page._selected_jaw_ids()
    if not selected_ids:
        QMessageBox.information(
            page,
            page._t('jaw_library.action.edit_jaw', 'Edit jaw'),
            page._t('jaw_library.message.select_jaw_first', 'Select a jaw first.'),
        )
        return
    if len(selected_ids) > 1:
        mode = ask_multi_edit_mode(page, len(selected_ids), page._t)
        if mode == 'batch':
            page._batch_edit_jaws(selected_ids)
        elif mode == 'group':
            page._group_edit_jaws(selected_ids)
        return
    jaw = page.jaw_service.get_jaw(selected_ids[0])
    dlg = AddEditJawDialog(page, jaw=jaw, translate=page._t)
    if dlg.exec() == QDialog.Accepted:
        save_from_dialog(page, dlg, original_jaw_id=jaw.get('jaw_id', ''))


def delete_jaw(page) -> None:
    if not page.current_jaw_id:
        QMessageBox.information(
            page,
            page._t('jaw_library.action.delete_jaw', 'Delete jaw'),
            page._t('jaw_library.message.select_jaw_first', 'Select a jaw first.'),
        )
        return

    box = QMessageBox(page)
    setup_editor_dialog(box)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle(page._t('jaw_library.action.delete_jaw', 'Delete jaw'))
    box.setText(page._t('jaw_library.message.delete_jaw_prompt', 'Delete jaw {jaw_id}?', jaw_id=page.current_jaw_id))
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

    deleted_id = page.current_jaw_id
    page.jaw_service.delete_jaw(deleted_id)
    page.item_deleted.emit(deleted_id)
    page.current_jaw_id = None
    page._current_item_id = None
    page.refresh_list()
    page.populate_details(None)


def copy_jaw(page) -> None:
    if not page.current_jaw_id:
        QMessageBox.information(
            page,
            page._t('jaw_library.action.copy_jaw', 'Copy jaw'),
            page._t('jaw_library.message.select_jaw_first', 'Select a jaw first.'),
        )
        return
    jaw = page.jaw_service.get_jaw(page.current_jaw_id)
    if not jaw:
        return

    new_id, accepted = prompt_text(
        page,
        page._t('jaw_library.action.copy_jaw', 'Copy jaw'),
        page._t('jaw_library.prompt.new_jaw_id', 'New Jaw ID:'),
    )
    if not accepted or not new_id.strip():
        return

    copied = dict(jaw)
    copied['jaw_id'] = new_id.strip()
    try:
        page.jaw_service.save_jaw(copied)
        page.current_jaw_id = copied['jaw_id']
        page._current_item_id = copied['jaw_id']
        page.refresh_list()
        page.populate_details(page.jaw_service.get_jaw(page.current_jaw_id))
    except ValueError as exc:
        QMessageBox.warning(page, page._t('jaw_library.action.copy_jaw', 'Copy jaw'), str(exc))


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
    return editor.text(), dlg.exec() == QDialog.Accepted
