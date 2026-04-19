"""UI layout builders for JawPage.

Extracted from jaw_page.py (Phase 5 Pass 7) to reduce page size.
All functions take the page object as their first argument and mutate
its attributes in place, matching the original inline structure.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
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
from shared.ui.helpers.page_scaffold_common import (
    apply_catalog_list_view_defaults,
    build_catalog_list_shell,
    build_catalog_splitter,
    build_detail_container_shell,
    build_page_root,
    build_search_input,
    install_catalog_list_event_filters,
)
from ui.jaw_page_support.catalog_list_widgets import JawCatalogListView
from ui.jaw_page_support.bottom_bars_builder import build_bottom_bars
from ui.jaw_page_support.selector_actions import update_selector_remove_button
from ui.jaw_page_support.selector_widgets import JawAssignmentSlot, SelectorRemoveDropButton
from ui.jaw_page_support.topbar_builder import build_filter_toolbar
from ui.shared.selector_panel_builders import (
    apply_selector_icon_button,
    build_selector_actions_row,
    build_selector_card_shell,
    build_selector_hint_label,
    build_selector_info_header,
    build_selector_toggle_button,
)

__all__ = [
    "build_jaw_page_layout",
]


def build_jaw_page_layout(page) -> None:
    """Build the full JawPage UI layout.

    Creates: search_input, filter_pane, sidebar, splitter, list view,
    detail container, selector card, bottom bars.  Called from
    JawPage._build_ui() so that the page file stays thin.
    """
    root = build_page_root(page)

    page.search_input = build_search_input(page)
    page.filter_pane = build_filter_toolbar(page)
    topbar_host = QWidget()
    topbar_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    topbar_host_layout = QVBoxLayout(topbar_host)
    topbar_host_layout.setContentsMargins(0, 0, 0, 4)
    topbar_host_layout.setSpacing(0)
    topbar_host_layout.addWidget(page.filter_pane)
    root.setSpacing(0)
    root.addWidget(topbar_host)

    content = QHBoxLayout()
    content.setContentsMargins(0, 0, 0, 0)
    content.setSpacing(10)

    page.view_buttons = []
    if page.show_sidebar:
        page.sidebar = QFrame()
        page.sidebar.setProperty('card', True)
        page.sidebar.setFixedWidth(188)
        side_layout = QVBoxLayout(page.sidebar)
        side_layout.setContentsMargins(10, 12, 10, 12)
        side_layout.setSpacing(6)

        side_title = QLabel(page._t('jaw_library.section.views', 'Jaw Views'))
        side_title.setProperty('detailSectionTitle', True)
        side_layout.addWidget(side_title)

        for _title, mode in page.NAV_MODES:
            btn = QPushButton(page._nav_mode_title(mode))
            btn.setProperty('panelActionButton', True)
            btn.clicked.connect(lambda _checked=False, m=mode: page._set_view_mode(m))
            side_layout.addWidget(btn)
            page.view_buttons.append((mode, btn))
        side_layout.addStretch(1)
        content.addWidget(page.sidebar, 0)

    page.splitter = build_catalog_splitter(_build_catalog_list_card(page), _build_detail_container(page))
    page.detail_container.hide()
    page.detail_header_container.hide()
    page.splitter.setSizes([1, 0])
    content.addWidget(page.splitter, 1)
    root.addLayout(content, 1)

    build_bottom_bars(page, root)
    page._set_view_mode('all', refresh=False)
    page._selector_slot_controller.refresh_selector_slots()
    update_selector_remove_button(page)
    _install_layout_event_filters(page)


# ---------------------------------------------------------------------------
# Private sub-builders
# ---------------------------------------------------------------------------

def _build_catalog_list_card(page) -> QWidget:
    """Build the catalog list card (list view + model wiring)."""
    list_card, list_layout = build_catalog_list_shell()

    page.list_view = JawCatalogListView()
    page.jaw_list = page.list_view
    apply_catalog_list_view_defaults(page.list_view)

    page._item_model = page._item_model or page._create_model()
    page._jaw_model = page._item_model
    page.list_view.setModel(page._item_model)
    page._jaw_delegate = page.create_delegate()
    page.list_view.setItemDelegate(page._jaw_delegate)
    page.list_view.clicked.connect(page._on_catalog_clicked)
    page.list_view.doubleClicked.connect(page.on_item_double_clicked)
    install_catalog_list_event_filters(page.list_view, page)
    page._connect_selection_model()

    list_layout.addWidget(page.list_view, 1)
    list_host = QWidget()
    list_host.setProperty('pageFamilyHost', True)
    list_host_layout = QVBoxLayout(list_host)
    list_host_layout.setContentsMargins(56, 40, 0, 0)
    list_host_layout.setSpacing(0)
    list_host_layout.addWidget(list_card)
    return list_host


def _build_detail_container(page) -> QWidget:
    """Build the detail container (scrollable detail panel + selector card)."""
    (
        page.detail_container,
        detail_layout,
        page.detail_card,
        page.detail_scroll,
        page.detail_panel,
        page.detail_layout,
    ) = build_detail_container_shell()
    page._detail_container_layout = detail_layout
    detail_layout.setContentsMargins(0, 8, 0, 0)
    detail_layout.addWidget(_build_selector_card(page), 1)

    page.populate_details(None)
    return page.detail_container


def _build_selector_card(page) -> QFrame:
    """Build the selector card (drag-and-drop spindle assignment UI)."""
    page.selector_card, page.selector_scroll, page.selector_panel, selector_layout = \
        build_selector_card_shell(spacing=8)
    selector_card_layout = QVBoxLayout(page.selector_card)
    selector_card_layout.setContentsMargins(0, 0, 0, 0)
    selector_card_layout.setSpacing(0)

    (
        page.selector_info_header,
        page.selector_header_title_label,
        page.selector_spindle_value_label,
        page.selector_module_value_label,
    ) = build_selector_info_header(
        title_text=page._t('jaw_library.selector.header_title', 'Jaw Selector'),
        left_badge_text='SP1',
        right_badge_text=page._t('tool_library.selector.jaws', 'Jaws'),
    )
    selector_layout.addWidget(page.selector_info_header, 0)

    ctx_row = QHBoxLayout()
    ctx_row.setContentsMargins(0, 0, 0, 0)
    ctx_row.setSpacing(10)
    ctx_row.addStretch(1)

    from ui.jaw_page_support.selector_actions import on_selector_toggle_clicked
    page.selector_toggle_btn = build_selector_toggle_button(
        text=page._t('tool_library.selector.mode_details', 'DETAILS'),
        on_clicked=lambda: on_selector_toggle_clicked(page),
    )

    ctx_row.addWidget(page.selector_toggle_btn, 0)
    ctx_row.addStretch(1)
    selector_layout.addLayout(ctx_row)

    page.selector_hint_label = build_selector_hint_label(
        text=page._t('tool_library.selector.jaw_hint', 'Drag jaws from the catalog to SP1 or SP2.'),
        multiline=True,
    )
    selector_layout.addWidget(page.selector_hint_label, 0)

    page.selector_sp1_slot = JawAssignmentSlot(
        'main',
        page._t('jaw_library.selector.sp1_slot', 'SP1 jaw'),
        translate=page._t,
    )
    page.selector_sp2_slot = JawAssignmentSlot(
        'sub',
        page._t('jaw_library.selector.sp2_slot', 'SP2 jaw'),
        translate=page._t,
    )
    page.selector_sp1_slot.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
    page.selector_sp2_slot.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
    page.selector_sp1_slot.set_drop_placeholder_text(page._t('jaw_library.selector.drop_here', 'Drop jaw here'))
    page.selector_sp2_slot.set_drop_placeholder_text(page._t('jaw_library.selector.drop_here', 'Drop jaw here'))
    page.selector_sp1_slot.jawDropped.connect(page._selector_slot_controller.on_selector_jaw_dropped)
    page.selector_sp2_slot.jawDropped.connect(page._selector_slot_controller.on_selector_jaw_dropped)
    page.selector_sp1_slot.slotClicked.connect(page._selector_slot_controller.on_selector_slot_clicked)
    page.selector_sp2_slot.slotClicked.connect(page._selector_slot_controller.on_selector_slot_clicked)
    selector_layout.addWidget(page.selector_sp1_slot, 0)
    selector_layout.addWidget(page.selector_sp2_slot, 0)
    selector_layout.addStretch(1)

    page.selector_remove_btn = SelectorRemoveDropButton()
    apply_selector_icon_button(
        page.selector_remove_btn,
        icon_path=TOOL_ICONS_DIR / 'delete.svg',
        tooltip=page._t('tool_library.selector.remove', 'Remove'),
        danger=True,
    )
    page.selector_remove_btn.clicked.connect(
        page._selector_slot_controller.remove_selected_selector_jaws
    )
    page.selector_remove_btn.jawsDropped.connect(
        page._selector_slot_controller.remove_selector_jaws_by_ids
    )
    selector_actions = build_selector_actions_row(spacing=4)
    selector_actions.addWidget(page.selector_remove_btn, 0, Qt.AlignLeft)
    selector_actions.addStretch(1)
    selector_layout.addLayout(selector_actions)

    page.selector_scroll.setWidget(page.selector_panel)
    selector_card_layout.addWidget(page.selector_scroll, 1)
    return page.selector_card


def _install_layout_event_filters(page) -> None:
    """Install event filters on all layout-level widgets."""
    for widget in (
        getattr(page, 'selector_card', None),
        getattr(page, 'selector_scroll', None) and page.selector_scroll.viewport(),
        getattr(page, 'selector_panel', None),
        getattr(page, 'detail_container', None),
        getattr(page, 'splitter', None),
        getattr(page, 'filter_pane', None),
        getattr(page, 'button_bar', None),
        getattr(page, 'selector_bottom_bar', None),
        getattr(page, 'detail_header_container', None),
    ):
        if widget is not None:
            widget.installEventFilter(page)
