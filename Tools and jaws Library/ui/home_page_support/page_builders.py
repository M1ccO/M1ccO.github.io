"""Page layout builders for HomePage.

Extracted from home_page.py (Phase 10 Pass 4).
Mirrors the jaw_page_support/page_builders.py pattern.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from shared.ui.helpers.page_scaffold_common import (
    apply_catalog_list_view_defaults,
    build_catalog_list_shell,
    build_catalog_splitter,
    build_detail_container_shell,
    build_page_root,
    build_search_input,
    install_catalog_list_event_filters,
)

__all__ = [
    "build_tool_page_layout",
    "build_catalog_list_card",
    "build_detail_container",
    "build_bottom_bars",
]


def build_tool_page_layout(page) -> None:
    """Build the full HomePage layout; called from HomePage._build_ui()."""
    root = build_page_root(page)

    page.search_input = build_search_input(page)

    page.filter_pane = page.build_filter_pane()
    root.addWidget(page.filter_pane)

    page.splitter = build_catalog_splitter(build_catalog_list_card(page), build_detail_container(page))
    root.addWidget(page.splitter, 1)

    build_bottom_bars(page, root)

    page.detail_container.hide()
    page.detail_header_container.hide()
    page.splitter.setSizes([1, 0])


def build_catalog_list_card(page) -> QFrame:
    """Build and return the catalog list card widget."""
    list_card, list_layout = build_catalog_list_shell()

    page.list_view = QListView()
    page.tool_list = page.list_view
    apply_catalog_list_view_defaults(page.list_view)

    page.list_view.setItemDelegate(page.create_delegate())
    page.list_view.clicked.connect(page._on_list_item_clicked)
    page.list_view.doubleClicked.connect(page.on_item_double_clicked)
    install_catalog_list_event_filters(page.list_view, page)

    list_layout.addWidget(page.list_view, 1)
    return list_card


def build_detail_container(page) -> QWidget:
    """Build and return the detail panel container widget."""
    (
        page.detail_container,
        detail_layout,
        page.detail_card,
        page.detail_scroll,
        page.detail_panel,
        page.detail_layout,
    ) = build_detail_container_shell()

    page.populate_details(None)
    return page.detail_container


def build_bottom_bars(page, root: QVBoxLayout) -> None:
    """Build the action button bar and hidden selector bar; add both to root layout."""
    page.button_bar = QFrame()
    page.button_bar.setProperty('bottomBar', True)
    actions = QHBoxLayout(page.button_bar)
    actions.setContentsMargins(10, 8, 10, 8)
    actions.setSpacing(8)

    page.edit_btn = QPushButton(page._t('tool_library.action.edit_tool', 'EDIT TOOL'))
    page.delete_btn = QPushButton(page._t('tool_library.action.delete_tool', 'DELETE TOOL'))
    page.add_btn = QPushButton(page._t('tool_library.action.add_tool', 'ADD TOOL'))
    page.copy_btn = QPushButton(page._t('tool_library.action.copy_tool', 'COPY TOOL'))
    for btn in (page.edit_btn, page.delete_btn, page.add_btn, page.copy_btn):
        btn.setProperty('panelActionButton', True)
    page.delete_btn.setProperty('dangerAction', True)
    page.add_btn.setProperty('primaryAction', True)

    page.edit_btn.clicked.connect(page.edit_tool)
    page.delete_btn.clicked.connect(page.delete_tool)
    page.add_btn.clicked.connect(page.add_tool)
    page.copy_btn.clicked.connect(page.copy_tool)

    page.module_switch_label = QLabel(page._t('tool_library.module.switch_to', 'Switch to'))
    page.module_switch_label.setProperty('pageSubtitle', True)
    page.module_toggle_btn = QPushButton(page._t('tool_library.module.jaws', 'JAWS'))
    page.module_toggle_btn.setProperty('panelActionButton', True)
    page.module_toggle_btn.setFixedHeight(28)
    page.module_toggle_btn.clicked.connect(
        lambda: page._module_switch_callback() if callable(page._module_switch_callback) else None
    )

    actions.addWidget(page.module_switch_label, 0, Qt.AlignLeft | Qt.AlignVCenter)
    actions.addWidget(page.module_toggle_btn, 0, Qt.AlignLeft | Qt.AlignVCenter)
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
    root.addWidget(page.selector_bottom_bar)
