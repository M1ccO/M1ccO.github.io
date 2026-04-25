"""CRUD action handlers for JawPage.

Extracted from jaw_page.py (Phase 5 Pass 8) to reduce page size.
All public functions take the page object as their first argument.
"""

from __future__ import annotations

from uuid import uuid4

from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from shared.ui.editor_launch_debug import (
    attach_editor_launch_id,
    clear_editor_launch_context,
    editor_launch_diag_enabled,
    editor_launch_debug,
    set_editor_launch_context,
)
from shared.ui.transition_shell import cancel_receiver_ready_signal
from shared.ui.runtime_trace import rtrace
from shared.ui.helpers.editor_helpers import (
    apply_modal_background_blur,
    ask_multi_edit_mode,
    clear_modal_background_blur,
    create_dialog_buttons,
    prompt_line_text,
    run_editor_modal,
    setup_editor_dialog,
)
from ui.jaw_page_support.detached_preview import close_detached_preview

__all__ = [
    "add_jaw",
    "copy_jaw",
    "delete_jaw",
    "edit_jaw",
    "prompt_text",
    "save_from_dialog",
]


AddEditJawDialog = None


def _jaw_editor_dialog_class():
    global AddEditJawDialog
    if AddEditJawDialog is None:
        from ui.jaw_editor_dialog import AddEditJawDialog as _AddEditJawDialog
        AddEditJawDialog = _AddEditJawDialog
    return AddEditJawDialog


def _build_stub_editor_dialog(page, title: str, launch_id: str, parent=None) -> QDialog:
    editor_launch_debug("crud.jaw.stub_dialog.build", launch_id=launch_id, title=title)
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
        "The real Jaw Editor class was not imported or constructed because "
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


def _dialog_visible(dlg) -> bool:
    is_visible = getattr(dlg, 'isVisible', None)
    return bool(is_visible()) if callable(is_visible) else False


def _attach_editor_modal_visual_state(dlg, host, blur_effect) -> None:
    if dlg is None:
        return
    try:
        dlg._editor_blur_host = host
        dlg._editor_blur_effect = None
        dlg._editor_blur_overlay = blur_effect
    except Exception:
        pass


def save_from_dialog(page, dlg, original_jaw_id: str | None = None) -> None:
    rtrace("jaw.save_from_dialog.entry", dlg_id=id(dlg), original_jaw_id=original_jaw_id, has_accepted_method=hasattr(dlg, 'get_accepted_jaw_data'), has_accepted_data=hasattr(dlg, '_accepted_jaw_data'))
    try:
        data = dlg.get_accepted_jaw_data() if hasattr(dlg, 'get_accepted_jaw_data') else dlg.get_jaw_data()
        rtrace(
            "jaw.save.begin",
            original_jaw_id=original_jaw_id,
            new_jaw_id=data.get('jaw_id'),
            stl_path_len=len(str(data.get('stl_path', ''))),
            has_accepted_method=hasattr(dlg, 'get_accepted_jaw_data'),
            keys=sorted(data.keys()),
        )
        page.jaw_service.save_jaw(data)
        new_jaw_id = data['jaw_id']
        if original_jaw_id and original_jaw_id != new_jaw_id:
            page.jaw_service.delete_jaw(original_jaw_id)
        page.current_jaw_id = new_jaw_id
        page._current_item_id = new_jaw_id
        rtrace("jaw.save.pre_refresh", new_jaw_id=new_jaw_id, initial_load_done=getattr(page, '_initial_load_done', None), page_visible=page.isVisible())
        page.refresh_catalog()
        readback = page.jaw_service.get_jaw(new_jaw_id) or {}
        rtrace(
            "jaw.save.post_refresh",
            new_jaw_id=new_jaw_id,
            readback_stl_len=len(str(readback.get('stl_path', ''))),
            readback_keys=sorted(readback.keys()) if isinstance(readback, dict) else None,
        )
        page.populate_details(readback if readback else None)
    except ValueError as exc:
        rtrace("jaw.save.value_error", err=str(exc))
        QMessageBox.warning(page, page._t('tool_library.error.invalid_data', 'Invalid data'), str(exc))
    except Exception as exc:
        rtrace("jaw.save.exception", err=str(exc), type=type(exc).__name__)
        QMessageBox.warning(page, page._t('tool_library.error.invalid_data', 'Invalid data'), str(exc))


def add_jaw(page) -> None:
    launch_id = f"jaw-add-{uuid4().hex[:8]}"
    if editor_launch_diag_enabled("NO_DIALOG"):
        editor_launch_debug("crud.add_jaw.no_dialog_bypass", launch_id=launch_id)
        return
    _close_open_preview(page)
    editor_launch_debug("crud.add_jaw.begin", launch_id=launch_id)
    editor_launch_debug("crud.add_jaw.dialog_init.before", launch_id=launch_id)
    host = getattr(page, 'window', lambda: None)()
    if host is None:
        try:
            host = page.window()
        except Exception:
            host = None
    _blur = None
    set_editor_launch_context(launch_id)
    try:
        if editor_launch_diag_enabled("STUB_EDITOR"):
            parent = host if editor_launch_diag_enabled("PARENTED_STUB_EDITOR") else None
            dlg = _build_stub_editor_dialog(page, page._t('jaw_editor.window_title.add', 'Add Jaw'), launch_id, parent=parent)
            stub_editor = True
        else:
            dlg = _jaw_editor_dialog_class()(translate=page._t)
            stub_editor = False
    finally:
        clear_editor_launch_context(launch_id)
    attach_editor_launch_id(dlg, launch_id)
    _attach_editor_modal_visual_state(dlg, host, _blur)
    editor_launch_debug("crud.add_jaw.dialog_init.after", launch_id=launch_id, visible=_dialog_visible(dlg))
    editor_launch_debug(
        "crud.add_jaw.host",
        launch_id=launch_id,
        host_visible=bool(host and host.isVisible()),
        host_active=bool(host and host.isActiveWindow()) if host else False,
        pending_sender_transition=bool(getattr(host, "_pending_sender_transition", None)) if host else False,
    )
    if editor_launch_diag_enabled("BYPASS_BLUR"):
        editor_launch_debug("crud.add_jaw.blur_bypassed", launch_id=launch_id)
    elif host and host.isVisible():
        try:
            _blur = apply_modal_background_blur(host, radius=6)
            editor_launch_debug(
                "crud.add_jaw.blur_applied",
                launch_id=launch_id,
                host_visible=host.isVisible(),
                host_active=host.isActiveWindow(),
                graphics_effect=type(_blur).__name__ if _blur else "",
            )
        except Exception:
            _blur = None
            editor_launch_debug("crud.add_jaw.blur_failed", launch_id=launch_id)
        _attach_editor_modal_visual_state(dlg, host, _blur)
        geom = host.frameGeometry()
        dlg.resize(1120, 760)
        x = geom.x() + max(0, (geom.width() - dlg.width()) // 2)
        y = geom.y() + max(0, (geom.height() - dlg.height()) // 2)
        dlg.move(x, y)
        editor_launch_debug("crud.add_jaw.positioned", launch_id=launch_id, x=x, y=y, width=dlg.width(), height=dlg.height())
    try:
        editor_launch_debug("crud.add_jaw.exec.before", launch_id=launch_id, visible=_dialog_visible(dlg))
        if run_editor_modal(dlg) == QDialog.Accepted and not stub_editor:
            editor_launch_debug("crud.add_jaw.exec.accepted", launch_id=launch_id)
            save_from_dialog(page, dlg)
        elif stub_editor:
            editor_launch_debug("crud.add_jaw.stub.closed", launch_id=launch_id)
        else:
            editor_launch_debug("crud.add_jaw.exec.rejected", launch_id=launch_id)
    finally:
        if _blur and host:
            try:
                clear_modal_background_blur(_blur)
                editor_launch_debug("crud.add_jaw.blur_cleared", launch_id=launch_id, host_visible=host.isVisible())
            except Exception:
                pass


def edit_jaw(page) -> None:
    rtrace("jaw.edit.entry", current_jaw_id=getattr(page, 'current_jaw_id', None))
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
    launch_id = f"jaw-edit-{uuid4().hex[:8]}"
    if editor_launch_diag_enabled("NO_DIALOG"):
        editor_launch_debug("crud.edit_jaw.no_dialog_bypass", launch_id=launch_id, jaw_id=jaw.get("jaw_id", ""))
        return
    _close_open_preview(page)
    editor_launch_debug("crud.edit_jaw.begin", launch_id=launch_id, jaw_id=jaw.get("jaw_id", ""))
    editor_launch_debug("crud.edit_jaw.dialog_init.before", launch_id=launch_id)
    _blur = None
    host = getattr(page, 'window', lambda: None)()
    if host is None:
        try:
            host = page.window()
        except Exception:
            host = None
    set_editor_launch_context(launch_id)
    try:
        if editor_launch_diag_enabled("STUB_EDITOR"):
            jaw_id = str(jaw.get('jaw_id') or '').strip()
            parent = host if editor_launch_diag_enabled("PARENTED_STUB_EDITOR") else None
            dlg = _build_stub_editor_dialog(page, page._t('jaw_editor.window_title.edit', 'Edit Jaw - {jaw_id}', jaw_id=jaw_id), launch_id, parent=parent)
            stub_editor = True
        else:
            dlg = _jaw_editor_dialog_class()(jaw=jaw, translate=page._t)
            stub_editor = False
    finally:
        clear_editor_launch_context(launch_id)
    attach_editor_launch_id(dlg, launch_id)
    _attach_editor_modal_visual_state(dlg, host, _blur)
    editor_launch_debug("crud.edit_jaw.dialog_init.after", launch_id=launch_id, visible=_dialog_visible(dlg))
    editor_launch_debug(
        "crud.edit_jaw.host",
        launch_id=launch_id,
        host_visible=bool(host and host.isVisible()),
        host_active=bool(host and host.isActiveWindow()) if host else False,
        pending_sender_transition=bool(getattr(host, "_pending_sender_transition", None)) if host else False,
    )
    if editor_launch_diag_enabled("BYPASS_BLUR"):
        editor_launch_debug("crud.edit_jaw.blur_bypassed", launch_id=launch_id)
    elif host and host.isVisible():
        try:
            _blur = apply_modal_background_blur(host, radius=6)
            editor_launch_debug(
                "crud.edit_jaw.blur_applied",
                launch_id=launch_id,
                host_visible=host.isVisible(),
                host_active=host.isActiveWindow(),
                graphics_effect=type(_blur).__name__ if _blur else "",
            )
        except Exception:
            _blur = None
            editor_launch_debug("crud.edit_jaw.blur_failed", launch_id=launch_id)
        _attach_editor_modal_visual_state(dlg, host, _blur)
        geom = host.frameGeometry()
        dlg.resize(1120, 760)
        x = geom.x() + max(0, (geom.width() - dlg.width()) // 2)
        y = geom.y() + max(0, (geom.height() - dlg.height()) // 2)
        dlg.move(x, y)
        editor_launch_debug("crud.edit_jaw.positioned", launch_id=launch_id, x=x, y=y, width=dlg.width(), height=dlg.height())
    try:
        editor_launch_debug("crud.edit_jaw.exec.before", launch_id=launch_id, visible=_dialog_visible(dlg))
        rtrace("jaw.edit.exec.before_call", dlg_id=id(dlg))
        try:
            exec_result = run_editor_modal(dlg)
        except Exception as exc:
            import traceback as _tb
            rtrace("jaw.edit.exec.raised", err=str(exc), type=type(exc).__name__, tb=_tb.format_exc())
            raise
        rtrace("jaw.edit.exec.returned", result=exec_result, accepted_const=int(QDialog.Accepted), has_accepted_data=hasattr(dlg, '_accepted_jaw_data'), dlg_id=id(dlg))
        if exec_result == QDialog.Accepted and not stub_editor:
            editor_launch_debug("crud.edit_jaw.exec.accepted", launch_id=launch_id)
            save_from_dialog(page, dlg, original_jaw_id=jaw.get('jaw_id', ''))
        elif stub_editor:
            editor_launch_debug("crud.edit_jaw.stub.closed", launch_id=launch_id)
        else:
            editor_launch_debug("crud.edit_jaw.exec.rejected", launch_id=launch_id)
    finally:
        if _blur and host:
            try:
                clear_modal_background_blur(_blur)
                editor_launch_debug("crud.edit_jaw.blur_cleared", launch_id=launch_id, host_visible=host.isVisible())
            except Exception:
                pass


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
    rtrace("jaw.delete.begin", jaw_id=deleted_id, initial_load_done=getattr(page, '_initial_load_done', None), page_visible=page.isVisible())
    page.jaw_service.delete_jaw(deleted_id)
    page.item_deleted.emit(deleted_id)
    page.current_jaw_id = None
    page._current_item_id = None
    before_rows = page._item_model.rowCount() if hasattr(page, '_item_model') else -1
    page.refresh_catalog()
    after_rows = page._item_model.rowCount() if hasattr(page, '_item_model') else -1
    rtrace(
        "jaw.delete.post_refresh",
        jaw_id=deleted_id,
        before_rows=before_rows,
        after_rows=after_rows,
        initial_load_done=getattr(page, '_initial_load_done', None),
        page_visible=page.isVisible(),
    )
    page.populate_details(None)


def copy_jaw(page) -> None:
    selected_ids = page._selected_jaw_ids()
    source_jaw_id = selected_ids[0] if selected_ids else page.current_jaw_id
    if not source_jaw_id:
        QMessageBox.information(
            page,
            page._t('jaw_library.action.copy_jaw', 'Copy jaw'),
            page._t('jaw_library.message.select_jaw_first', 'Select a jaw first.'),
        )
        return
    jaw = page.jaw_service.get_jaw(source_jaw_id)
    if not jaw:
        return

    rtrace("jaw.copy.prompt.before", source_jaw_id=source_jaw_id, prompt_func="prompt_line_text")
    try:
        new_id, accepted = prompt_text(
            page,
            page._t('jaw_library.action.copy_jaw', 'Copy jaw'),
            page._t('jaw_library.prompt.new_jaw_id', 'New Jaw ID:'),
        )
    except Exception as exc:
        rtrace("jaw.copy.prompt.raised", err=str(exc), type=type(exc).__name__)
        QMessageBox.warning(page, page._t('jaw_library.action.copy_jaw', 'Copy jaw'), str(exc))
        return
    rtrace("jaw.copy.prompt.after", accepted=accepted, new_id=new_id)
    if not accepted or not new_id.strip():
        return

    copied = dict(jaw)
    copied['jaw_id'] = new_id.strip()
    try:
        rtrace("jaw.copy.save.before_save", new_id=copied['jaw_id'])
        page.jaw_service.save_jaw(copied)
        rtrace("jaw.copy.save.after_save")
        page.current_jaw_id = copied['jaw_id']
        page._current_item_id = copied['jaw_id']
        rtrace("jaw.copy.save.before_refresh")
        page.refresh_catalog()
        rtrace("jaw.copy.save.after_refresh")
        got = page.jaw_service.get_jaw(page.current_jaw_id)
        rtrace("jaw.copy.save.before_populate", got_keys=sorted(got.keys()) if got else None)
        page.populate_details(got)
        rtrace("jaw.copy.save.after_populate")
    except ValueError as exc:
        rtrace("jaw.copy.save.value_error", err=str(exc))
        QMessageBox.warning(page, page._t('jaw_library.action.copy_jaw', 'Copy jaw'), str(exc))
    except Exception as exc:
        import traceback as _tb
        rtrace("jaw.copy.save.exception", err=str(exc), type=type(exc).__name__, tb=_tb.format_exc())
        QMessageBox.warning(page, page._t('jaw_library.action.copy_jaw', 'Copy jaw'), str(exc))


def prompt_text(page, title: str, label: str, initial: str = '') -> tuple[str, bool]:
    return prompt_line_text(page, title, label, initial, translate=page._t)
