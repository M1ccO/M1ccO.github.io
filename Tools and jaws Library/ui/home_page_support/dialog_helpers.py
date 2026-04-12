"""Generic dialog helper functions for confirmation and text-input prompts."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from shared.ui.helpers.editor_helpers import (
    apply_secondary_button_theme,
    create_dialog_buttons,
    setup_editor_dialog,
)


def prompt_text(
    parent: QWidget,
    translate: Callable[[str, str | None], str],
    title: str,
    label: str,
    initial: str = '',
) -> tuple[str, bool]:
    """Show a modal text-input dialog.

    Returns ``(text, accepted)`` where *accepted* is ``True`` when the user
    pressed OK and ``False`` when they cancelled.
    """
    dlg = QDialog(parent)
    setup_editor_dialog(dlg)
    dlg.setWindowTitle(title)
    dlg.setModal(True)

    root = QVBoxLayout(dlg)
    root.setContentsMargins(12, 12, 12, 12)
    root.setSpacing(8)

    prompt = QLabel(label)
    prompt.setProperty('detailFieldKey', True)
    prompt.setWordWrap(True)
    root.addWidget(prompt)

    editor = QLineEdit()
    editor.setText(initial)
    root.addWidget(editor)

    buttons = create_dialog_buttons(
        dlg,
        save_text=translate('common.ok', 'OK'),
        cancel_text=translate('common.cancel', 'Cancel'),
        on_save=dlg.accept,
        on_cancel=dlg.reject,
    )
    root.addWidget(buttons)

    apply_secondary_button_theme(dlg, buttons.button(QDialogButtonBox.Save))
    editor.setFocus()
    editor.selectAll()

    accepted = dlg.exec() == QDialog.Accepted
    return editor.text(), accepted


def confirm_yes_no(
    parent: QWidget,
    translate: Callable[[str, str | None], str],
    title: str,
    text: str,
    *,
    danger: bool,
) -> bool:
    """Show a Yes/No confirmation dialog.

    When *danger* is ``True`` the Yes button is styled as a destructive action.
    Returns ``True`` if the user clicked Yes.
    """
    box = QMessageBox(parent)
    setup_editor_dialog(box)
    box.setIcon(QMessageBox.Warning if danger else QMessageBox.Question)
    box.setWindowTitle(title)
    main_text = text
    info_text = ''
    if '\n\n' in text:
        main_text, info_text = text.split('\n\n', 1)
    box.setText(main_text)
    if info_text:
        box.setInformativeText(info_text)
        box.setStyleSheet(
            '#qt_msgbox_informativelabel { font-style: italic; font-weight: 400; color: #5f6a74; }'
        )
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

    yes_btn = box.button(QMessageBox.Yes)
    no_btn = box.button(QMessageBox.No)
    if yes_btn is not None:
        yes_btn.setText(translate('common.yes', 'Yes'))
        yes_btn.setProperty('panelActionButton', True)
        yes_btn.setProperty('dangerAction', bool(danger))
        yes_btn.setProperty('primaryAction', not danger)
    if no_btn is not None:
        no_btn.setText(translate('common.no', 'No'))
        no_btn.setProperty('panelActionButton', True)
        no_btn.setProperty('secondaryAction', True)

    return box.exec() == QMessageBox.Yes


__all__ = ["confirm_yes_no", "prompt_text"]
