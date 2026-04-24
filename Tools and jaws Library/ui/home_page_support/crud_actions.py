"""CRUD action handlers for HomePage.

Extracted from home_page.py (Phase 10 Pass 2).
All public functions take the page object as their first argument.
"""

from __future__ import annotations

from uuid import uuid4
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
from shared.ui.editor_launch_debug import (
    attach_editor_launch_id,
    clear_editor_launch_context,
    editor_launch_diag_enabled,
    editor_launch_debug,
    set_editor_launch_context,
)
from shared.ui.transition_shell import cancel_receiver_ready_signal
from shared.ui.helpers.editor_helpers import (
    apply_secondary_button_theme,
    ask_multi_edit_mode,
    create_dialog_buttons,
    setup_editor_dialog,
)
from ui.home_page_support.detached_preview import close_detached_preview

__all__ = ["add_tool", "copy_tool", "delete_tool", "edit_tool", "save_from_dialog"]


def _tool_editor_dialog_class():
    from ui.tool_editor_dialog import AddEditToolDialog
    return AddEditToolDialog


def _build_stub_editor_dialog(page, title: str, launch_id: str, parent=None) -> QDialog:
    editor_launch_debug("crud.tool.stub_dialog.build", launch_id=launch_id, title=title)
    dlg = QDialog(parent)
    setup_editor_dialog(dlg)
    dlg.setWindowTitle(title)
    dlg.resize(520, 220)
    dlg.setModal(True)

    root = QVBoxLayout(dlg)
    root.setContentsMargins(18, 18, 18, 18)
    root.setSpacing(10)
    label = QLabel(
        "Diagnostic stub editor.\n\n"
        "The real Tool Editor class was not imported or constructed because "
        "NTX_EDITOR_DIAG_STUB_EDITOR=1 is enabled."
    )
    label.setWordWrap(True)
    label.setProperty('detailHint', True)
    root.addWidget(label, 1)
    buttons = create_dialog_buttons(
        dlg,
        save_text=page._t('common.close', 'Close'),
        cancel_text=page._t('common.cancel', 'Cancel'),
        on_save=dlg.reject,
        on_cancel=dlg.reject,
    )
    root.addWidget(buttons)
    return dlg


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
        data = dlg.get_accepted_tool_data() if hasattr(dlg, 'get_accepted_tool_data') else dlg.get_tool_data()
        saved_uid = page.tool_service.save_tool(data)
        page.refresh_catalog()
        return int(saved_uid)
    except ValueError as exc:
        QMessageBox.warning(page, page._t('tool_library.error.invalid_data', 'Invalid data'), str(exc))
    except Exception as exc:
        QMessageBox.warning(page, page._t('tool_library.error.invalid_data', 'Invalid data'), str(exc))
    return None


def add_tool(page) -> None:
    """Open AddEditToolDialog in 'add' mode."""
    launch_id = f"tool-add-{uuid4().hex[:8]}"
    if editor_launch_diag_enabled("NO_DIALOG"):
        editor_launch_debug("crud.add_tool.no_dialog_bypass", launch_id=launch_id)
        return
    _close_open_preview(page)
    host = getattr(page, 'window', lambda: None)()
    if host is None:
        try:
            host = page.window()
        except Exception:
            host = None
    editor_launch_debug(
        "crud.add_tool.begin",
        launch_id=launch_id,
        host_visible=bool(host and host.isVisible()),
        host_active=bool(host and host.isActiveWindow()) if host else False,
        pending_sender_transition=bool(getattr(host, "_pending_sender_transition", None)) if host else False,
    )

    _blur = None
    if editor_launch_diag_enabled("BYPASS_BLUR"):
        editor_launch_debug("crud.add_tool.blur_bypassed", launch_id=launch_id)
    elif host and host.isVisible():
        try:
            from PySide6.QtWidgets import QGraphicsBlurEffect
            _blur = QGraphicsBlurEffect(host)
            _blur.setBlurRadius(6)
            host.setGraphicsEffect(_blur)
            editor_launch_debug(
                "crud.add_tool.blur_applied",
                launch_id=launch_id,
                host_visible=host.isVisible(),
                host_active=host.isActiveWindow(),
                graphics_effect=type(host.graphicsEffect()).__name__ if host.graphicsEffect() else "",
            )
        except Exception:
            _blur = None
            editor_launch_debug("crud.add_tool.blur_failed", launch_id=launch_id)

    editor_launch_debug("crud.add_tool.dialog_init.before", launch_id=launch_id)
    set_editor_launch_context(launch_id)
    try:
        if editor_launch_diag_enabled("STUB_EDITOR"):
            parent = host if editor_launch_diag_enabled("PARENTED_STUB_EDITOR") else None
            dlg = _build_stub_editor_dialog(page, page._t('tool_editor.window_title.add', 'Add Tool'), launch_id, parent=parent)
            stub_editor = True
        else:
            dlg = _tool_editor_dialog_class()(
                tool=None,
                tool_service=page.tool_service,
                translate=page._t,
            )
            stub_editor = False
    finally:
        clear_editor_launch_context(launch_id)
    attach_editor_launch_id(dlg, launch_id)
    editor_launch_debug("crud.add_tool.dialog_init.after", launch_id=launch_id, visible=dlg.isVisible())

    if host and host.isVisible():
        geom = host.frameGeometry()
        dlg.resize(1120, 760)
        x = geom.x() + max(0, (geom.width() - dlg.width()) // 2)
        y = geom.y() + max(0, (geom.height() - dlg.height()) // 2)
        dlg.move(x, y)
        editor_launch_debug("crud.add_tool.positioned", launch_id=launch_id, x=x, y=y, width=dlg.width(), height=dlg.height())
    try:
        editor_launch_debug("crud.add_tool.exec.before", launch_id=launch_id, visible=dlg.isVisible())
        if dlg.exec() == QDialog.Accepted and not stub_editor:
            editor_launch_debug("crud.add_tool.exec.accepted", launch_id=launch_id)
            saved_uid = save_from_dialog(page, dlg)
            if saved_uid:
                page._restore_selection_by_uid(saved_uid)
        elif stub_editor:
            editor_launch_debug("crud.add_tool.stub.closed", launch_id=launch_id)
        else:
            editor_launch_debug("crud.add_tool.exec.rejected", launch_id=launch_id)
    finally:
        if _blur and host:
            try:
                host.setGraphicsEffect(None)
                editor_launch_debug("crud.add_tool.blur_cleared", launch_id=launch_id, host_visible=host.isVisible())
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

    launch_id = f"tool-edit-{uuid4().hex[:8]}"
    if editor_launch_diag_enabled("NO_DIALOG"):
        editor_launch_debug("crud.edit_tool.no_dialog_bypass", launch_id=launch_id, tool_id=tool.get("id", ""), uid=tool.get("uid", ""))
        return
    _close_open_preview(page)
    host = getattr(page, 'window', lambda: None)()
    if host is None:
        try:
            host = page.window()
        except Exception:
            host = None
    editor_launch_debug("crud.edit_tool.begin", launch_id=launch_id, tool_id=tool.get("id", ""), uid=tool.get("uid", ""))
    editor_launch_debug("crud.edit_tool.dialog_init.before", launch_id=launch_id)
    set_editor_launch_context(launch_id)
    try:
        if editor_launch_diag_enabled("STUB_EDITOR"):
            tool_id = str(tool.get('id') or '').strip()
            parent = host if editor_launch_diag_enabled("PARENTED_STUB_EDITOR") else None
            dlg = _build_stub_editor_dialog(page, page._t('tool_editor.window_title.edit', 'Edit Tool - {tool_id}', tool_id=tool_id), launch_id, parent=parent)
            stub_editor = True
        else:
            dlg = _tool_editor_dialog_class()(
                tool=tool,
                tool_service=page.tool_service,
                translate=page._t,
            )
            stub_editor = False
    finally:
        clear_editor_launch_context(launch_id)
    attach_editor_launch_id(dlg, launch_id)
    editor_launch_debug("crud.edit_tool.dialog_init.after", launch_id=launch_id, visible=dlg.isVisible())
    editor_launch_debug(
        "crud.edit_tool.host",
        launch_id=launch_id,
        host_visible=bool(host and host.isVisible()),
        host_active=bool(host and host.isActiveWindow()) if host else False,
        pending_sender_transition=bool(getattr(host, "_pending_sender_transition", None)) if host else False,
    )
    _blur = None
    if editor_launch_diag_enabled("BYPASS_BLUR"):
        editor_launch_debug("crud.edit_tool.blur_bypassed", launch_id=launch_id)
    elif host and host.isVisible():
        try:
            from PySide6.QtWidgets import QGraphicsBlurEffect
            _blur = QGraphicsBlurEffect(host)
            _blur.setBlurRadius(6)
            host.setGraphicsEffect(_blur)
            editor_launch_debug(
                "crud.edit_tool.blur_applied",
                launch_id=launch_id,
                host_visible=host.isVisible(),
                host_active=host.isActiveWindow(),
                graphics_effect=type(host.graphicsEffect()).__name__ if host.graphicsEffect() else "",
            )
        except Exception:
            _blur = None
            editor_launch_debug("crud.edit_tool.blur_failed", launch_id=launch_id)
        geom = host.frameGeometry()
        dlg.resize(1120, 760)
        x = geom.x() + max(0, (geom.width() - dlg.width()) // 2)
        y = geom.y() + max(0, (geom.height() - dlg.height()) // 2)
        dlg.move(x, y)
        editor_launch_debug("crud.edit_tool.positioned", launch_id=launch_id, x=x, y=y, width=dlg.width(), height=dlg.height())
    saved_uid = None
    try:
        editor_launch_debug("crud.edit_tool.exec.before", launch_id=launch_id, visible=dlg.isVisible())
        if dlg.exec() == QDialog.Accepted and not stub_editor:
            editor_launch_debug("crud.edit_tool.exec.accepted", launch_id=launch_id)
            saved_uid = save_from_dialog(page, dlg)
        elif stub_editor:
            editor_launch_debug("crud.edit_tool.stub.closed", launch_id=launch_id)
        else:
            editor_launch_debug("crud.edit_tool.exec.rejected", launch_id=launch_id)
    finally:
        if _blur and host:
            try:
                host.setGraphicsEffect(None)
                editor_launch_debug("crud.edit_tool.blur_cleared", launch_id=launch_id, host_visible=host.isVisible())
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

    page.refresh_catalog()


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

    page.refresh_catalog()
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

    captured: list[str] = []
    buttons.accepted.connect(lambda: captured.append(editor.text()))

    accepted = dlg.exec() == QDialog.Accepted
    return captured[0] if captured else '', accepted


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
        dlg = _tool_editor_dialog_class()(
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
            page.refresh_catalog()
            return

        saved_before.append(dict(tool))
        page.tool_service.save_tool(dlg.get_accepted_tool_data() if hasattr(dlg, 'get_accepted_tool_data') else dlg.get_tool_data())

    page.refresh_catalog()


def _group_edit_tools(page, tool_uids: list[int]) -> None:
    _close_open_preview(page)
    parent = _prepare_modal_host_window(page)
    dlg = _tool_editor_dialog_class()(
        parent=parent,
        tool_service=page.tool_service,
        translate=page._t,
        group_edit_mode=True,
        group_count=len(tool_uids),
    )
    baseline = dlg.get_tool_data()
    if dlg.exec() != QDialog.Accepted:
        return

    edited_data = dlg.get_accepted_tool_data() if hasattr(dlg, 'get_accepted_tool_data') else dlg.get_tool_data()
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

    page.refresh_catalog()
