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
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config import TOOL_ICONS_DIR
from shared.ui.helpers.editor_helpers import (
    create_titled_section,
    style_icon_action_button,
    style_move_arrow_button,
    style_panel_action_button,
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
from ui.home_page_support.catalog_list_widgets import ToolCatalogListView
from ui.home_page_support.selector_widgets import (
    ToolAssignmentListWidget,
    ToolSelectorRemoveDropButton,
)
from ui.shared.selector_panel_builders import (
    build_selector_actions_row,
    build_selector_card_shell,
    build_selector_info_header,
    build_selector_toggle_button,
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

    page.list_view = ToolCatalogListView()
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

    page._detail_container_layout = detail_layout
    detail_layout.addWidget(_build_selector_card(page), 1)

    page.populate_details(None)
    return page.detail_container


def _build_selector_card(page) -> QFrame:
    """Build selector side-panel card for tool selector mode."""
    page.selector_card, page.selector_scroll, page.selector_panel, selector_layout = \
        build_selector_card_shell(spacing=8)
    selector_card_layout = QVBoxLayout(page.selector_card)
    selector_card_layout.setContentsMargins(0, 0, 0, 0)
    selector_card_layout.setSpacing(0)

    (
        page.selector_info_header,
        page.selector_header_title_label,
        page.selector_spindle_value_label,
        page.selector_head_value_label,
    ) = build_selector_info_header(
        title_text=page._t('tool_library.selector.header_title', 'Tool Selector'),
        left_badge_text='SP1',
        right_badge_text='HEAD1',
    )
    selector_layout.addWidget(page.selector_info_header, 0)

    ctx_row = QHBoxLayout()
    ctx_row.setContentsMargins(0, 0, 0, 0)
    ctx_row.setSpacing(10)
    ctx_row.addStretch(1)

    page.selector_toggle_btn = build_selector_toggle_button(
        text=page._t('tool_library.selector.mode_details', 'DETAILS'),
        on_clicked=page._on_selector_toggle_clicked,
    )
    ctx_row.addWidget(page.selector_toggle_btn, 0)

    page.selector_spindle_btn = QPushButton('SP1')
    page.selector_spindle_btn.setProperty('panelActionButton', True)
    page.selector_spindle_btn.setCheckable(True)
    page.selector_spindle_btn.setMinimumWidth(120)
    page.selector_spindle_btn.setMaximumWidth(140)
    page.selector_spindle_btn.setFixedHeight(30)
    page.selector_spindle_btn.setProperty('spindle', 'main')
    page.selector_spindle_btn.clicked.connect(page._toggle_selector_spindle)
    style_panel_action_button(page.selector_spindle_btn)
    ctx_row.addWidget(page.selector_spindle_btn, 0)

    ctx_row.addStretch(1)
    selector_layout.addLayout(ctx_row)

    page.selector_drop_hint = QLabel(
        page._t(
            'tool_library.selector.drop_hint',
            'Drag tools from the catalog to this list and reorder them by dragging.',
        )
    )
    page.selector_drop_hint.setWordWrap(True)
    page.selector_drop_hint.setProperty('detailHint', True)
    selector_layout.addWidget(page.selector_drop_hint, 0)

    page.selector_assignment_list = ToolAssignmentListWidget()
    page.selector_assignment_list.setObjectName('toolIdsOrderList')
    page.selector_assignment_list.setStyleSheet(
        '#toolIdsOrderList { background: transparent; border: none; }'
        '#toolIdsOrderList::viewport { background: transparent; border: none; }'
        '#toolIdsOrderList::item { background: transparent; border: none; }'
    )
    page.selector_assignment_list.externalToolsDropped.connect(page._on_selector_tools_dropped)
    page.selector_assignment_list.orderChanged.connect(page._sync_selector_assignment_order)
    page.selector_assignment_list.itemSelectionChanged.connect(page._update_selector_assignment_buttons)
    page.selector_assignment_list.itemSelectionChanged.connect(page._sync_selector_card_selection_states)

    page.selector_assignments_frame = create_titled_section(
        page._t('tool_library.selector.head1_tools', 'Head 1 Tools')
    )
    page.selector_assignments_frame.setProperty('selectorAssignmentsFrame', True)
    page.selector_assignments_frame.setProperty('toolIdsPanel', True)
    page.selector_assignments_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    selector_assignments_layout = QVBoxLayout(page.selector_assignments_frame)
    selector_assignments_layout.setContentsMargins(8, 10, 8, 8)
    selector_assignments_layout.setSpacing(0)
    selector_assignments_layout.addWidget(page.selector_assignment_list, 1)
    selector_layout.addWidget(page.selector_assignments_frame, 1)

    selector_actions = build_selector_actions_row(spacing=4)

    page.selector_move_up_btn = QPushButton('▲')
    style_move_arrow_button(
        page.selector_move_up_btn,
        '▲',
        page._t('tool_library.selector.move_up', 'Move Up'),
    )
    page.selector_move_up_btn.clicked.connect(page._move_selector_up)
    selector_actions.addWidget(page.selector_move_up_btn)

    page.selector_move_down_btn = QPushButton('▼')
    style_move_arrow_button(
        page.selector_move_down_btn,
        '▼',
        page._t('tool_library.selector.move_down', 'Move Down'),
    )
    page.selector_move_down_btn.clicked.connect(page._move_selector_down)
    selector_actions.addWidget(page.selector_move_down_btn)

    page.selector_remove_btn = ToolSelectorRemoveDropButton()
    style_icon_action_button(
        page.selector_remove_btn,
        TOOL_ICONS_DIR / 'delete.svg',
        page._t('tool_library.selector.remove', 'Remove'),
        danger=True,
    )
    page.selector_remove_btn.clicked.connect(page._remove_selector_assignment)
    page.selector_remove_btn.toolsDropped.connect(page._remove_selector_assignments_by_drop)
    selector_actions.addWidget(page.selector_remove_btn)

    page.selector_comment_btn = QPushButton()
    style_icon_action_button(
        page.selector_comment_btn,
        TOOL_ICONS_DIR / 'comment.svg',
        page._t('tool_library.selector.add_comment', 'Add Comment'),
    )
    page.selector_comment_btn.clicked.connect(page._add_selector_comment)
    selector_actions.addWidget(page.selector_comment_btn)

    page.selector_delete_comment_btn = QPushButton()
    style_icon_action_button(
        page.selector_delete_comment_btn,
        TOOL_ICONS_DIR / 'comment_disable.svg',
        page._t('tool_library.selector.delete_comment', 'Delete Comment'),
    )
    page.selector_delete_comment_btn.clicked.connect(page._delete_selector_comment)
    selector_actions.addWidget(page.selector_delete_comment_btn)

    selector_actions.addStretch(1)
    selector_layout.addLayout(selector_actions)

    page.selector_scroll.setWidget(page.selector_panel)
    selector_card_layout.addWidget(page.selector_scroll, 1)
    page.selector_assignment_list.clear()
    return page.selector_card


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
    sel_bar_layout = QHBoxLayout(page.selector_bottom_bar)
    sel_bar_layout.setContentsMargins(10, 8, 10, 8)
    sel_bar_layout.setSpacing(8)
    sel_bar_layout.addStretch(1)

    page.selector_cancel_btn = QPushButton(page._t('tool_library.selector.cancel', 'CANCEL'))
    page.selector_cancel_btn.setProperty('panelActionButton', True)
    page.selector_cancel_btn.clicked.connect(page._on_selector_cancel)
    sel_bar_layout.addWidget(page.selector_cancel_btn)

    page.selector_done_btn = QPushButton(page._t('tool_library.selector.done', 'DONE'))
    page.selector_done_btn.setProperty('panelActionButton', True)
    page.selector_done_btn.setProperty('primaryAction', True)
    page.selector_done_btn.clicked.connect(page._on_selector_done)
    sel_bar_layout.addWidget(page.selector_done_btn)

    root.addWidget(page.selector_bottom_bar)
