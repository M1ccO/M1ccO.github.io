from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from config import TOOL_ICONS_DIR
from shared.ui.helpers.editor_helpers import style_icon_action_button, style_panel_action_button
from shared.ui.helpers.page_scaffold_common import (
    apply_catalog_list_view_defaults,
    build_catalog_list_shell,
    build_detail_container_shell,
)
from shared.ui.helpers.topbar_common import (
    build_detail_header,
    build_details_toggle,
    build_filter_frame,
    build_filter_reset,
    build_preview_toggle,
    build_search_toggle,
    rebuild_filter_row,
)
from ui.widgets.common import apply_shared_dropdown_style
from ui.jaw_catalog_delegate import JawCatalogDelegate
from ui.jaw_page_support.catalog_list_widgets import JawCatalogListView
from ui.jaw_page_support.selector_widgets import JawAssignmentSlot, SelectorRemoveDropButton
from ui.shared.selector_panel_builders import (
    build_selector_actions_row,
    build_selector_card_shell,
    build_selector_hint_label,
    build_selector_info_header,
)
from ui.selectors.common import build_selector_bottom_bar


class JawSelectorLayoutMixin:

    def _build_toolbar(self, root: QVBoxLayout) -> None:
        """Build the shared filter toolbar matching the library style."""
        frame, self._filter_layout = build_filter_frame()
        # Dialog has no left rail — clear the page-specific objectName and margins
        frame.setObjectName('')
        self._filter_layout.setContentsMargins(8, 6, 8, 6)

        search_icon = QIcon(str(TOOL_ICONS_DIR / 'search_icon.svg'))
        self._close_icon = QIcon(str(TOOL_ICONS_DIR / 'close_icon.svg'))

        self.search_toggle = build_search_toggle(search_icon, self._toggle_search)

        # Details toggle → switches right panel between selector and jaw details
        self.toggle_details_btn = build_details_toggle(TOOL_ICONS_DIR, self._toggle_detail_panel)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            self._t('jaw_library.search.placeholder', 'Search jaw ID, type, spindle side, diameter...')
        )
        self.search_input.textChanged.connect(self._refresh_catalog)
        self.search_input.setVisible(False)

        self.filter_icon = build_filter_reset(TOOL_ICONS_DIR, self._clear_search)

        self.view_filter = QComboBox()
        self.view_filter.setObjectName('topTypeFilter')
        self.view_filter.addItem(self._t('jaw_library.nav.all_jaws', 'All Jaws'), 'all')
        self.view_filter.addItem(self._t('jaw_library.nav.main_spindle', 'Main Spindle'), 'main')
        self.view_filter.addItem(self._t('jaw_library.nav.sub_spindle', 'Sub Spindle'), 'sub')
        self.view_filter.addItem(self._t('jaw_library.nav.soft_jaws', 'Soft Jaws'), 'soft')
        self.view_filter.addItem(self._t('jaw_library.nav.hard_group', 'Hard / Spiked / Special'), 'hard_group')
        self.view_filter.currentIndexChanged.connect(self._refresh_catalog)
        apply_shared_dropdown_style(self.view_filter)

        # Preview toggle: hidden — no detached window in selector yet
        self.preview_window_btn = build_preview_toggle(
            TOOL_ICONS_DIR,
            self._t('tool_library.preview.toggle', 'Toggle detached 3D preview'),
            self.toggle_preview_window,
        )
        self.preview_window_btn.setVisible(True)

        # Right-side detail header shown when detail panel is active
        self.detail_header_container, self.detail_section_label, self.detail_close_btn = \
            build_detail_header(
                self._close_icon,
                self._t('jaw_library.section.jaw_details', 'Jaw details'),
                self._switch_to_selector_panel,
            )
        self.detail_header_container.setVisible(False)

        rebuild_filter_row(
            self._filter_layout,
            self.search_toggle,
            self.toggle_details_btn,
            self.search_input,
            self.filter_icon,
            [self.view_filter],
            self.preview_window_btn,
            self.detail_header_container,
        )

        root.addWidget(frame, 0)

    # Keep old name as alias so the dialog __init__ still works
    def _build_filter_row(self, root: QVBoxLayout) -> None:
        self._build_toolbar(root)

    def _build_content(self, root: QVBoxLayout) -> None:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)

        list_card, list_layout = build_catalog_list_shell()
        self.list_view = JawCatalogListView()
        apply_catalog_list_view_defaults(self.list_view)
        self._model = QStandardItemModel(self.list_view)
        self.list_view.setModel(self._model)
        self.list_view.setItemDelegate(JawCatalogDelegate(parent=self.list_view, translate=self._t))
        self.list_view.doubleClicked.connect(self._on_catalog_double_clicked_open_detail)
        self.list_view.clicked.connect(self._on_catalog_item_clicked)
        list_layout.addWidget(self.list_view, 1)
        splitter.addWidget(list_card)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._build_selector_card(), 1)
        right_layout.addWidget(self._build_detail_card(), 1)
        splitter.addWidget(right_panel)

        splitter.setSizes([int(self.width() * 0.58), int(self.width() * 0.42)])
        root.addWidget(splitter, 1)

    def _build_detail_card(self) -> QWidget:
        """Build the switchable detail panel using the shared container shell."""
        (
            detail_container,
            _outer_layout,
            _card,
            _scroll,
            _panel,
            self.detail_layout,
        ) = build_detail_container_shell(min_width=300)
        self.detail_card = detail_container
        self.detail_card.setVisible(False)
        return self.detail_card

    def _build_selector_card(self):
        selector_card, selector_scroll, selector_panel, selector_layout = build_selector_card_shell(spacing=8)
        selector_card.setVisible(True)
        self.selector_card = selector_card
        selector_card_layout = QVBoxLayout(selector_card)
        selector_card_layout.setContentsMargins(0, 0, 0, 0)
        selector_card_layout.setSpacing(0)

        (
            self.selector_info_header,
            self.selector_header_title_label,
            self.selector_spindle_value_label,
            self.selector_module_value_label,
        ) = build_selector_info_header(
            title_text=self._t('jaw_library.selector.header_title', 'Jaw Selector'),
            left_badge_text='SP1',
            right_badge_text=self._t('tool_library.selector.jaws', 'Jaws'),
            fixed_height_policy=True,
        )
        selector_layout.addWidget(self.selector_info_header, 0)

        hint = build_selector_hint_label(
            text=self._t('tool_library.selector.jaw_hint', 'Drag jaws from the catalog to SP1 or SP2.'),
            multiline=False,
        )
        selector_layout.addWidget(hint, 0)

        self.slot_main = JawAssignmentSlot(
            'main',
            self._t('jaw_library.selector.sp1_slot', 'SP1 jaw'),
            translate=self._t,
        )
        self.slot_sub = JawAssignmentSlot(
            'sub',
            self._t('jaw_library.selector.sp2_slot', 'SP2 jaw'),
            translate=self._t,
        )
        self.slot_main.set_drop_placeholder_text(self._t('jaw_library.selector.drop_here', 'Drop jaw here'))
        self.slot_sub.set_drop_placeholder_text(self._t('jaw_library.selector.drop_here', 'Drop jaw here'))
        self.slot_main.jawDropped.connect(self._on_slot_dropped)
        self.slot_sub.jawDropped.connect(self._on_slot_dropped)
        self.slot_main.slotClicked.connect(self._on_slot_clicked)
        self.slot_sub.slotClicked.connect(self._on_slot_clicked)
        selector_layout.addWidget(self.slot_main, 0)
        selector_layout.addWidget(self.slot_sub, 0)
        selector_layout.addStretch(1)

        self.remove_btn = SelectorRemoveDropButton()
        style_icon_action_button(
            self.remove_btn,
            TOOL_ICONS_DIR / 'delete.svg',
            self._t('tool_library.selector.remove', 'Remove'),
            danger=True,
        )
        self.remove_btn.clicked.connect(self._remove_selected)
        self.remove_btn.jawsDropped.connect(self._remove_by_ids)

        actions = build_selector_actions_row(spacing=4)
        actions.addWidget(self.remove_btn, 0, Qt.AlignLeft)
        actions.addStretch(1)
        selector_layout.addLayout(actions)

        selector_scroll.setWidget(selector_panel)
        selector_card_layout.addWidget(selector_scroll, 1)
        return selector_card

    def _build_bottom_bar(self, root: QVBoxLayout) -> None:
        build_selector_bottom_bar(
            root,
            translate=self._translate,
            on_cancel=self._cancel,
            on_done=self._send_selector_selection,
        )

