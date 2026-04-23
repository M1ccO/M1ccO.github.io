"""Page layout builders for HomePage.

Extracted from home_page.py (Phase 10 Pass 4).
Mirrors the jaw_page_support/page_builders.py pattern.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from shared.ui.editor_launch_debug import (
    cleanup_hidden_orphan_top_levels,
    editor_launch_diag_enabled,
    editor_launch_debug,
    start_editor_window_probe,
)
from shared.ui.layout_contract import get_container_layout_contract
from shared.ui.helpers.page_scaffold_common import (
    apply_catalog_list_view_defaults,
    build_catalog_list_shell,
    build_catalog_splitter,
    build_detail_container_shell,
    build_page_root,
    build_search_input,
    install_catalog_list_event_filters,
)
from ui.home_page_support.catalog_list_widgets import ToolCatalogListView

__all__ = [
    "build_tool_page_layout",
    "build_catalog_list_card",
    "build_detail_container",
    "build_bottom_bars",
]


def _connect_or_log(page, *, action_name: str, callback, log_event: str) -> None:
    if editor_launch_diag_enabled("NOOP_BUTTONS"):
        callback = lambda: editor_launch_debug(log_event)

    def _wrapped_action() -> None:
        host = None
        try:
            host = page.window()
        except Exception:
            host = page
        cleanup_hidden_orphan_top_levels(host, reason=f"tool.{action_name}")
        start_editor_window_probe(host, f"tool.{action_name}")
        callback()

    setattr(page, action_name, _wrapped_action)


def _install_keyboard_only_actions(page) -> None:
    if not editor_launch_diag_enabled("KEYBOARD_ONLY_ACTIONS"):
        return

    for btn in (page.add_btn, page.edit_btn, page.delete_btn, page.copy_btn):
        btn.hide()
        btn.setEnabled(False)

    page._diag_tool_edit_shortcut = QShortcut(QKeySequence("Ctrl+Alt+E"), page.button_bar)
    page._diag_tool_edit_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
    page._diag_tool_edit_shortcut.activated.connect(getattr(page, "_diag_edit_action"))

    page._diag_tool_add_shortcut = QShortcut(QKeySequence("Ctrl+Alt+N"), page.button_bar)
    page._diag_tool_add_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
    page._diag_tool_add_shortcut.activated.connect(getattr(page, "_diag_add_action"))


def build_tool_page_layout(page) -> None:
    """Build the full HomePage layout; called from HomePage._build_ui()."""
    contract = get_container_layout_contract()
    root = build_page_root(page)

    page.search_input = build_search_input(page)

    page.filter_pane = page.build_filter_pane()

    list_card_widget = build_catalog_list_card(page)
    left_panel = QWidget()
    left_panel_layout = QVBoxLayout(left_panel)
    left_panel_layout.setContentsMargins(0, contract.content_top_inset, 0, 0)
    left_panel_layout.setSpacing(contract.content_section_spacing)
    left_panel_layout.addWidget(page.filter_pane)
    left_panel_layout.addWidget(list_card_widget, 1)

    root.setSpacing(0)
    page.splitter = build_catalog_splitter(left_panel, build_detail_container(page))
    root.addWidget(page.splitter, 1)

    build_bottom_bars(page, root)

    page.detail_container.hide()
    page.detail_header_container.hide()
    page.splitter.setSizes([1, 0])


def build_catalog_list_card(page) -> QFrame:
    """Build and return the catalog list card widget."""
    contract = get_container_layout_contract()
    list_card, list_layout = build_catalog_list_shell()

    page.list_view = ToolCatalogListView()
    page.tool_list = page.list_view
    apply_catalog_list_view_defaults(page.list_view)

    page.list_view.setItemDelegate(page.create_delegate())
    page.list_view.clicked.connect(page._on_list_item_clicked)
    page.list_view.doubleClicked.connect(page.on_item_double_clicked)
    install_catalog_list_event_filters(page.list_view, page)

    list_layout.addWidget(page.list_view, 1)
    list_host = QWidget()
    list_host.setProperty('pageFamilyHost', True)
    list_host_layout = QVBoxLayout(list_host)
    list_host_layout.setContentsMargins(*contract.frame_host_margins)
    list_host_layout.setSpacing(0)
    list_host_layout.addWidget(list_card)
    return list_host


def build_detail_container(page) -> QWidget:
    """Build and return the detail panel container widget."""
    contract = get_container_layout_contract()
    (
        page.detail_container,
        detail_layout,
        page.detail_card,
        page.detail_scroll,
        page.detail_panel,
        page.detail_layout,
    ) = build_detail_container_shell()

    page._detail_container_layout = detail_layout
    filter_height = 0
    if getattr(page, "filter_pane", None) is not None:
        filter_height = max(0, page.filter_pane.sizeHint().height())
    detail_top = (
        contract.content_top_inset
        + filter_height
        + contract.content_section_spacing
        + contract.frame_host_margins[1]
    )
    detail_layout.setContentsMargins(0, detail_top, 0, 0)

    page.populate_details(None)
    return page.detail_container


def build_bottom_bars(page, root: QVBoxLayout) -> None:
    """Build the action button bar and add it to root layout."""
    contract = get_container_layout_contract()
    page.button_bar = QFrame()
    page.button_bar.setProperty('bottomBar', True)
    actions = QHBoxLayout(page.button_bar)
    actions.setContentsMargins(*contract.bottom_bar_margins)
    actions.setSpacing(8)

    page.edit_btn = QPushButton(page._t('tool_library.action.edit_tool', 'EDIT TOOL'))
    page.delete_btn = QPushButton(page._t('tool_library.action.delete_tool', 'DELETE TOOL'))
    page.add_btn = QPushButton(page._t('tool_library.action.add_tool', 'ADD TOOL'))
    page.copy_btn = QPushButton(page._t('tool_library.action.copy_tool', 'COPY TOOL'))
    for btn in (page.edit_btn, page.delete_btn, page.add_btn, page.copy_btn):
        btn.setProperty('panelActionButton', True)
    page.delete_btn.setProperty('dangerAction', True)
    page.add_btn.setProperty('primaryAction', True)

    _connect_or_log(
        page,
        action_name="_diag_edit_action",
        callback=page.edit_tool,
        log_event="diag.home.edit_btn.noop",
    )
    _connect_or_log(
        page,
        action_name="_diag_delete_action",
        callback=page.delete_tool,
        log_event="diag.home.delete_btn.noop",
    )
    _connect_or_log(
        page,
        action_name="_diag_add_action",
        callback=page.add_tool,
        log_event="diag.home.add_btn.noop",
    )
    _connect_or_log(
        page,
        action_name="_diag_copy_action",
        callback=page.copy_tool,
        log_event="diag.home.copy_btn.noop",
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
