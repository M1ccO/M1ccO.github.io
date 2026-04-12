"""Bottom action bar builders for HomePage."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from .selector_actions import on_selector_cancel, on_selector_done, update_selector_assignment_buttons


def build_bottom_bars(page, *, root: QVBoxLayout) -> None:
    """Build normal and selector-mode bottom action bars."""
    page.button_bar = QFrame()
    page.button_bar.setProperty("bottomBar", True)
    button_layout = QHBoxLayout(page.button_bar)
    button_layout.setContentsMargins(10, 8, 10, 8)
    button_layout.setSpacing(8)

    page.copy_btn = QPushButton(page._t("tool_library.action.copy_tool", "COPY TOOL"))
    page.copy_btn.setProperty("panelActionButton", True)
    page.copy_btn.clicked.connect(page.copy_tool)
    page.edit_btn = QPushButton(page._t("tool_library.action.edit_tool", "EDIT TOOL"))
    page.edit_btn.setProperty("panelActionButton", True)
    page.edit_btn.clicked.connect(page.edit_tool)
    page.delete_btn = QPushButton(page._t("tool_library.action.delete_tool", "DELETE TOOL"))
    page.delete_btn.setProperty("panelActionButton", True)
    page.delete_btn.setProperty("dangerAction", True)
    page.delete_btn.clicked.connect(page.delete_tool)
    page.add_btn = QPushButton(page._t("tool_library.action.add_tool", "ADD TOOL"))
    page.add_btn.setProperty("panelActionButton", True)
    page.add_btn.setProperty("primaryAction", True)
    page.add_btn.clicked.connect(page.add_tool)

    page.module_switch_label = QLabel(page._t("tool_library.module.switch_to", "Switch to"))
    page.module_switch_label.setProperty("pageSubtitle", True)
    page.module_toggle_btn = QPushButton(page._t("tool_library.module.jaws", "JAWS"))
    page.module_toggle_btn.setProperty("panelActionButton", True)
    page.module_toggle_btn.setFixedHeight(28)
    page.module_toggle_btn.clicked.connect(
        lambda: page._module_switch_callback() if callable(page._module_switch_callback) else None
    )

    button_layout.addWidget(page.module_switch_label, 0, Qt.AlignLeft | Qt.AlignVCenter)
    button_layout.addWidget(page.module_toggle_btn, 0, Qt.AlignLeft | Qt.AlignVCenter)
    button_layout.addStretch(1)
    page.selection_count_label = QLabel("")
    page.selection_count_label.setProperty("detailHint", True)
    page.selection_count_label.setStyleSheet("background: transparent; border: none;")
    page.selection_count_label.hide()
    button_layout.addWidget(page.selection_count_label, 0, Qt.AlignBottom)
    button_layout.addWidget(page.add_btn)
    button_layout.addWidget(page.edit_btn)
    button_layout.addWidget(page.delete_btn)
    button_layout.addWidget(page.copy_btn)
    root.addWidget(page.button_bar)

    page.selector_bottom_bar = QFrame()
    page.selector_bottom_bar.setProperty("bottomBar", True)
    page.selector_bottom_bar.setVisible(False)
    sel_bar_layout = QHBoxLayout(page.selector_bottom_bar)
    sel_bar_layout.setContentsMargins(10, 8, 10, 8)
    sel_bar_layout.setSpacing(8)
    sel_bar_layout.addStretch(1)

    page.selector_cancel_btn = QPushButton(page._t("tool_library.selector.cancel", "CANCEL"))
    page.selector_cancel_btn.setProperty("panelActionButton", True)
    page.selector_cancel_btn.clicked.connect(lambda: on_selector_cancel(page))
    sel_bar_layout.addWidget(page.selector_cancel_btn)

    page.selector_done_btn = QPushButton(page._t("tool_library.selector.done", "DONE"))
    page.selector_done_btn.setProperty("panelActionButton", True)
    page.selector_done_btn.setProperty("primaryAction", True)
    page.selector_done_btn.clicked.connect(lambda: on_selector_done(page))
    sel_bar_layout.addWidget(page.selector_done_btn)
    root.addWidget(page.selector_bottom_bar)

    update_selector_assignment_buttons(page)
