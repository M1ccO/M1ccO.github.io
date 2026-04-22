"""CRUD action handlers for HomePage.

Extracted from home_page.py (Phase 10 Pass 2).
All public functions take the page object as their first argument.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from shared.data.backup_helpers import create_db_backup
from shared.ui.transition_shell import cancel_receiver_ready_signal
from shared.ui.helpers.editor_helpers import (
    apply_secondary_button_theme,
    ask_multi_edit_mode,
    create_dialog_buttons,
    setup_editor_dialog,
)
from ui.home_page_support.detached_preview import close_detached_preview
from ui.tool_editor_dialog import AddEditToolDialog

__all__ = ["add_tool", "copy_tool", "delete_tool", "edit_tool", "save_from_dialog"]


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
    return page


def _close_open_preview(page) -> None:
    preview_btn = getattr(page, 'preview_window_btn', None)
    if preview_btn is None or not preview_btn.isChecked():
        return
    close_detached_preview(page)


def save_from_dialog(page, dlg) -> int | None:
    """Validate + persist tool data from dialog; return saved uid on success."""
    try:
        data = dlg.get_tool_data()
        saved_uid = page.tool_service.save_tool(data)
        page.refresh_list()
        return int(saved_uid)
    except ValueError as exc:
        QMessageBox.warning(page, page._t('tool_library.error.invalid_data', 'Invalid data'), str(exc))
    except Exception as exc:
        QMessageBox.warning(page, page._t('tool_library.error.invalid_data', 'Invalid data'), str(exc))
    return None


def add_tool(page) -> None:
    """Open AddEditToolDialog in 'add' mode."""
    _close_open_preview(page)
    dlg = AddEditToolDialog(
        tool=None,
        tool_service=page.tool_service,
        translate=page._t,
    )
    host = getattr(page, 'window', lambda: None)()
    if host is None:
        try:
            host = page.window()
        except Exception:
            host = None
    _blur = None
    if host and host.isVisible():
        try:
            from PySide6.QtWidgets import QGraphicsBlurEffect
            _blur = QGraphicsBlurEffect(host)
            _blur.setBlurRadius(6)
            host.setGraphicsEffect(_blur)
        except Exception:
            _blur = None
        geom = host.frameGeometry()
        dlg.resize(1120, 760)
        x = geom.x() + max(0, (geom.width() - dlg.width()) // 2)
        y = geom.y() + max(0, (geom.height() - dlg.height()) // 2)
        dlg.move(x, y)
    try:
        if dlg.exec() == QDialog.Accepted:
            saved_uid = save_from_dialog(page, dlg)
            if saved_uid:
                page._restore_selection_by_uid(saved_uid)
    finally:
        if _blur and host:
            try:
                host.setGraphicsEffect(None)
            except Exception:
                pass


def edit_tool(page) -> None:
    """Open AddEditToolDialog in 'edit' mode for selected tool."""
    selected_uids = page._selected_tool_uids()
    if not selected_uids:
        tool = page._get_selected_tool()
        if tool and tool.get('uid'):
            selected_uids = [int(tool['uid'])]

    if not selected_uids:
        QMessageBox.information(
            page,
            page._t('tool_library.message.edit_tool', 'Edit tool'),
            page._t('tool_library.message.select_tool_first', 'Select a tool first.'),
        )
        return

    if len(selected_uids) > 1:
        mode = ask_multi_edit_mode(page, len(selected_uids), page._t)
        if mode == 'batch':
            _batch_edit_tools(page, selected_uids)
        elif mode == 'group':
            _group_edit_tools(page, selected_uids)
        return

    tool = page.tool_service.get_tool_by_uid(int(selected_uids[0]))
    if not tool:
        QMessageBox.information(
            page,
            page._t('tool_library.message.edit_tool', 'Edit tool'),
            page._t('tool_library.message.select_tool_first', 'Select a tool first.'),
        )
        return

    _close_open_preview(page)
    dlg = AddEditToolDialog(
        tool=tool,
        tool_service=page.tool_service,
        translate=page._t,
    )
    host = getattr(page, 'window', lambda: None)()
    if host is None:
        try:
            host = page.window()
        except Exception:
            host = None
    _blur = None
    if host and host.isVisible():
        try:
            from PySide6.QtWidgets import QGraphicsBlurEffect
            _blur = QGraphicsBlurEffect(host)
            _blur.setBlurRadius(6)
            host.setGraphicsEffect(_blur)
        except Exception:
            _blur = None
        geom = host.frameGeometry()
        dlg.resize(1120, 760)
        x = geom.x() + max(0, (geom.width() - dlg.width()) // 2)
        y = geom.y() + max(0, (geom.height() - dlg.height()) // 2)
        dlg.move(x, y)
    try:
        if dlg.exec() == QDialog.Accepted:
            saved_uid = save_from_dialog(page, dlg)
    finally:
        if _blur and host:
            try:
                host.setGraphicsEffect(None)
            except Exception:
                pass
        if saved_uid:
            page._restore_selection_by_uid(saved_uid)


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
    selected_uids = page._selected_tool_uids()
    if not selected_uids:
        tool = page._get_selected_tool()
        if tool and tool.get('uid'):
            selected_uids = [int(tool['uid'])]

    if not selected_uids:
        QMessageBox.information(
            page,
            page._t('tool_library.message.copy_tool', 'Copy tool'),
            page._t('tool_library.message.select_tool_first', 'Select a tool first.'),
        )
        return

    source_uid = int(selected_uids[0])
    source_tool = page.tool_service.get_tool_by_uid(source_uid)
    if not source_tool:
        QMessageBox.warning(
            page,
            page._t('tool_library.message.copy_tool', 'Copy tool'),
            page._t('tool_library.error.invalid_data', 'Invalid data'),
        )
        return

    source_id = str(source_tool.get('id') or '').strip()
    initial_id = f"{source_id}_copy" if source_id else ''
    new_id, accepted = _prompt_text(
        page,
        page._t('tool_library.message.copy_tool', 'Copy tool'),
        page._t('tool_library.prompt.new_tool_id', 'New Tool ID:'),
        initial=initial_id,
    )
    if not accepted:
        return

    target_id = new_id.strip()
    if not target_id:
        QMessageBox.warning(
            page,
            page._t('tool_library.message.copy_tool', 'Copy tool'),
            page._t('tool_library.error.invalid_data', 'Invalid data'),
        )
        return

    try:
        copied = page.tool_service.copy_tool_by_uid(source_uid, target_id)
    except ValueError as exc:
        QMessageBox.warning(page, page._t('tool_library.message.copy_tool', 'Copy tool'), str(exc))
        return

    page.refresh_list()
    copied_uid = int(copied.get('uid') or 0) if isinstance(copied, dict) else 0
    if copied_uid:
        page._restore_selection_by_uid(copied_uid)


def _prompt_text(page, title: str, label: str, initial: str = '') -> tuple[str, bool]:
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


def _backup(page, tag: str) -> Path:
    return create_db_backup(Path(page.tool_service.db.path), tag)


def _prompt_batch_cancel_behavior(page) -> str:
    box = QMessageBox(page)
    box.setIcon(QMessageBox.Question)
    box.setWindowTitle(page._t('tool_library.batch.cancel.title', 'Batch edit cancelled'))
    box.setText(
        page._t(
            'tool_library.batch.cancel.body',
            "You stopped editing partway through the batch. Do you want to keep the changes you've already saved, or undo all of them?",
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


def _batch_edit_tools(page, tool_uids: list[int]) -> None:
    _close_open_preview(page)
    parent = _prepare_modal_host_window(page)
    saved_before: list[dict] = []
    total = len(tool_uids)
    for idx, tool_uid in enumerate(tool_uids, 1):
        tool = page.tool_service.get_tool_by_uid(int(tool_uid))
        if not tool:
            continue
        dlg = AddEditToolDialog(
            parent=parent,
            tool=tool,
            tool_service=page.tool_service,
            translate=page._t,
            batch_label=f"{idx}/{total}",
        )
        if dlg.exec() != QDialog.Accepted:
            if saved_before:
                action = _prompt_batch_cancel_behavior(page)
                if action == 'undo':
                    for previous in reversed(saved_before):
                        page.tool_service.save_tool(previous)
            page.refresh_list()
            return

        saved_before.append(dict(tool))
        page.tool_service.save_tool(dlg.get_tool_data())

    page.refresh_list()


def _group_edit_tools(page, tool_uids: list[int]) -> None:
    _close_open_preview(page)
    parent = _prepare_modal_host_window(page)
    dlg = AddEditToolDialog(
        parent=parent,
        tool_service=page.tool_service,
        translate=page._t,
        group_edit_mode=True,
        group_count=len(tool_uids),
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
    changed_fields.pop('id', None)
    changed_fields.pop('uid', None)
    if not changed_fields:
        QMessageBox.information(
            page,
            page._t('tool_library.group_edit.no_changes_title', 'No changes'),
            page._t('tool_library.group_edit.no_changes_body', 'No fields were changed.'),
        )
        return

    _backup(page, 'group_edit')
    for tool_uid in tool_uids:
        tool = page.tool_service.get_tool_by_uid(int(tool_uid))
        if not tool:
            continue
        updated = dict(tool)
        updated.update(changed_fields)
        updated['uid'] = int(tool_uid)
        updated['id'] = str(tool.get('id') or '')
        page.tool_service.save_tool(updated)

    page.refresh_list()
