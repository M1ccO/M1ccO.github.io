"""Bottom action bar builders for JawPage."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


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

    page.edit_btn.clicked.connect(page.edit_jaw)
    page.delete_btn.clicked.connect(page.delete_jaw)
    page.add_btn.clicked.connect(page.add_jaw)
    page.copy_btn.clicked.connect(page.copy_jaw)

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