"""Bottom action bar builders for JawPage."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from shared.ui.editor_launch_debug import (
    cleanup_hidden_orphan_top_levels,
    editor_launch_diag_enabled,
    editor_launch_debug,
    start_editor_window_probe,
)


def _connect_or_log(page, *, action_name: str, callback, log_event: str) -> None:
    if editor_launch_diag_enabled("NOOP_BUTTONS"):
        callback = lambda: editor_launch_debug(log_event)

    def _wrapped_action() -> None:
        host = None
        try:
            host = page.window()
        except Exception:
            host = page
        cleanup_hidden_orphan_top_levels(host, reason=f"jaw.{action_name}")
        start_editor_window_probe(host, f"jaw.{action_name}")
        callback()

    setattr(page, action_name, _wrapped_action)


def _install_keyboard_only_actions(page) -> None:
    if not editor_launch_diag_enabled("KEYBOARD_ONLY_ACTIONS"):
        return

    for btn in (page.add_btn, page.edit_btn, page.delete_btn, page.copy_btn):
        btn.hide()
        btn.setEnabled(False)

    page._diag_jaw_edit_shortcut = QShortcut(QKeySequence("Ctrl+Alt+E"), page.button_bar)
    page._diag_jaw_edit_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
    page._diag_jaw_edit_shortcut.activated.connect(getattr(page, "_diag_edit_action"))

    page._diag_jaw_add_shortcut = QShortcut(QKeySequence("Ctrl+Alt+N"), page.button_bar)
    page._diag_jaw_add_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
    page._diag_jaw_add_shortcut.activated.connect(getattr(page, "_diag_add_action"))


def build_bottom_bars(page, root: QVBoxLayout) -> None:
    page.button_bar = QFrame()
    page.button_bar.setProperty('bottomBar', True)
    actions = QHBoxLayout(page.button_bar)
    actions.setContentsMargins(10, 10, 10, 6)
    actions.setSpacing(8)

    page.edit_btn = QPushButton(page._t('jaw_library.action.edit_jaw_button', 'EDIT JAW'))
    page.delete_btn = QPushButton(page._t('jaw_library.action.delete_jaw_button', 'DELETE JAW'))
    page.add_btn = QPushButton(page._t('jaw_library.action.add_jaw_button', 'ADD JAW'))
    page.copy_btn = QPushButton(page._t('jaw_library.action.copy_jaw_button', 'COPY JAW'))
    for btn in (page.edit_btn, page.delete_btn, page.add_btn, page.copy_btn):
        btn.setProperty('panelActionButton', True)
    page.delete_btn.setProperty('dangerAction', True)
    page.add_btn.setProperty('primaryAction', True)

    _connect_or_log(
        page,
        action_name="_diag_edit_action",
        callback=page.edit_jaw,
        log_event="diag.jaw.edit_btn.noop",
    )
    _connect_or_log(
        page,
        action_name="_diag_delete_action",
        callback=page.delete_jaw,
        log_event="diag.jaw.delete_btn.noop",
    )
    _connect_or_log(
        page,
        action_name="_diag_add_action",
        callback=page.add_jaw,
        log_event="diag.jaw.add_btn.noop",
    )
    _connect_or_log(
        page,
        action_name="_diag_copy_action",
        callback=page.copy_jaw,
        log_event="diag.jaw.copy_btn.noop",
    )

    page.edit_btn.clicked.connect(page._diag_edit_action)
    page.delete_btn.clicked.connect(page._diag_delete_action)
    page.add_btn.clicked.connect(page._diag_add_action)
    page.copy_btn.clicked.connect(page._diag_copy_action)

    page.module_switch_label = QLabel('')
    page.module_switch_label.setVisible(False)
    page.module_toggle_btn = QPushButton('')
    page.module_toggle_btn.setVisible(False)
    page.module_toggle_btn.clicked.connect(
        lambda: page._module_switch_callback() if callable(page._module_switch_callback) else None
    )

    actions.addStretch(1)

    page.selection_count_label = QLabel('')
    page.selection_count_label.setProperty('detailHint', True)
    page.selection_count_label.setStyleSheet('background: transparent; border: none;')
    page.selection_count_label.hide()

    actions.addWidget(page.selection_count_label, 0, Qt.AlignBottom)
    actions.addWidget(page.add_btn)
    actions.addWidget(page.edit_btn)
    actions.addWidget(page.delete_btn)
    actions.addWidget(page.copy_btn)
    _install_keyboard_only_actions(page)
    root.addWidget(page.button_bar)

    page.selector_bottom_bar = QFrame()
    page.selector_bottom_bar.setProperty('bottomBar', True)
    page.selector_bottom_bar.setVisible(False)
    sel_bar_layout = QHBoxLayout(page.selector_bottom_bar)
    sel_bar_layout.setContentsMargins(10, 8, 10, 8)
    sel_bar_layout.setSpacing(8)
    sel_bar_layout.addStretch(1)

    page.selector_cancel_btn = QPushButton(page._t('tool_library.selector.cancel', 'CANCEL'))
    page.selector_cancel_btn.setProperty('panelActionButton', True)
    page.selector_cancel_btn.clicked.connect(lambda: page._on_selector_cancel())
    sel_bar_layout.addWidget(page.selector_cancel_btn)

    page.selector_done_btn = QPushButton(page._t('tool_library.selector.done', 'DONE'))
    page.selector_done_btn.setProperty('panelActionButton', True)
    page.selector_done_btn.setProperty('primaryAction', True)
    page.selector_done_btn.clicked.connect(lambda: page._on_selector_done())
    sel_bar_layout.addWidget(page.selector_done_btn)
    root.addWidget(page.selector_bottom_bar)


def retranslate_bottom_bars(page) -> None:
    page.edit_btn.setText(page._t('jaw_library.action.edit_jaw_button', 'EDIT JAW'))
    page.delete_btn.setText(page._t('jaw_library.action.delete_jaw_button', 'DELETE JAW'))
    page.add_btn.setText(page._t('jaw_library.action.add_jaw_button', 'ADD JAW'))
    page.copy_btn.setText(page._t('jaw_library.action.copy_jaw_button', 'COPY JAW'))
    page.selector_cancel_btn.setText(page._t('tool_library.selector.cancel', 'CANCEL'))
    page.selector_done_btn.setText(page._t('tool_library.selector.done', 'DONE'))
    page.module_switch_label.setText(page._t('tool_library.module.switch_to', 'Switch to'))


__all__ = ['build_bottom_bars', 'retranslate_bottom_bars']
