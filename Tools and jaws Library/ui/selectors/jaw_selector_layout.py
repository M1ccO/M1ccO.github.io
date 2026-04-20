from __future__ import annotations

from PySide6.QtCore import QSize, Qt
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

try:
    from ...config import TOOL_ICONS_DIR
except ImportError:
    from config import TOOL_ICONS_DIR
from shared.ui.helpers.editor_helpers import style_icon_action_button, style_panel_action_button
from shared.ui.helpers.icon_loader import icon_from_path
from shared.ui.helpers.page_scaffold_common import (
    apply_catalog_list_view_defaults,
    build_catalog_list_shell,
    build_detail_container_shell,
)
from shared.ui.theme import apply_top_level_surface_palette
from shared.ui.helpers.topbar_common import (
    build_detail_header,
    build_details_toggle,
    build_filter_frame,
    build_filter_reset,
    build_preview_toggle,
    build_search_toggle,
    rebuild_filter_row,
)
from ..widgets.common import apply_shared_dropdown_style
from ..jaw_catalog_delegate import JawCatalogDelegate
from ..jaw_page_support.catalog_list_widgets import JawCatalogListView
from ..jaw_page_support.selector_widgets import JawAssignmentSlot, SelectorRemoveDropButton
from ..shared.selector_panel_builders import (
    build_selector_actions_row,
    build_selector_card_shell,
    build_selector_hint_label,
    build_selector_info_header,
)
from .common import build_selector_bottom_bar


class JawSelectorLayoutMixin:

    def _build_toolbar(self, root: QVBoxLayout) -> None:
        """Build the shared filter toolbar matching the library style."""
        frame, self._filter_layout = build_filter_frame(parent=self)
        frame.setProperty('card', False)
        frame.setProperty('pageFamilyHost', True)
        apply_top_level_surface_palette(frame, role='page_bg')
        self._filter_layout.setContentsMargins(8, 6, 8, 6)

        search_icon = icon_from_path(TOOL_ICONS_DIR / 'search_icon.svg', size=QSize(28, 28))
        self._close_icon = icon_from_path(TOOL_ICONS_DIR / 'close_icon.svg', size=QSize(20, 20))

        self.search_toggle = build_search_toggle(search_icon, self._toggle_search)

        # Details toggle → switches right panel between selector and jaw details
        self.toggle_details_btn = build_details_toggle(TOOL_ICONS_DIR, self._toggle_detail_panel)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            self._t(
                'work_editor.jaw.filter_placeholder',
                'Hae leukien ID:tä, tyyppiä, karaa tai halkaisijaa...',
            )
        )
        self.search_input.textChanged.connect(self._refresh_catalog)
        self.search_input.setVisible(False)

        self.filter_icon = build_filter_reset(TOOL_ICONS_DIR, self._clear_search)

        self.view_filter = QComboBox()
        self.view_filter.setObjectName('topTypeFilter')
        self.view_filter.addItem(self._t('tool_library.nav.all_jaws', 'Kaikki leuat'), 'all')
        self.view_filter.addItem(self._t('work_editor.selector.sp1', 'Pääkara'), 'main')
        self.view_filter.addItem(self._t('work_editor.selector.sp2', 'Vastakara'), 'sub')
        self.view_filter.addItem(self._t('jaw_library.nav.soft_jaws', 'Pehmeät leuat'), 'soft')
        self.view_filter.addItem(self._t('jaw_library.nav.hard_group', 'Kovat / teräkäs / erikois'), 'hard_group')
        self.view_filter.currentIndexChanged.connect(self._refresh_catalog)
        apply_shared_dropdown_style(self.view_filter)

        # Preview toggle: hidden — no detached window in selector yet
        self.preview_window_btn = build_preview_toggle(
            TOOL_ICONS_DIR,
            self._t('tool_library.preview.toggle', 'Näytä irrotettava 3D-esikatselu'),
            self.toggle_preview_window,
        )
        preview_allowed = not bool(getattr(self, '_embedded_mode', False))
        self.preview_window_btn.setVisible(preview_allowed)
        self.preview_window_btn.setEnabled(preview_allowed)

        # Right-side detail header shown when detail panel is active
        self.detail_header_container, self.detail_section_label, self.detail_close_btn = \
            build_detail_header(
                self._close_icon,
                self._t('work_editor.selector.assignment.details_title', 'Leukojen tiedot'),
                self._switch_to_selector_panel,
                parent=frame,
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
        splitter.setObjectName('selectorSplitter')
        splitter.setProperty('pageFamilySplitter', True)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)
        splitter.setAutoFillBackground(False)

        list_card, list_layout = build_catalog_list_shell(parent=splitter)
        self.list_view = JawCatalogListView()
        apply_catalog_list_view_defaults(self.list_view)
        self._model = QStandardItemModel(self.list_view)
        self.list_view.setModel(self._model)
        self.list_view.setItemDelegate(JawCatalogDelegate(parent=self.list_view, translate=self._t))
        self.list_view.doubleClicked.connect(self._on_catalog_double_clicked_open_detail)
        self.list_view.clicked.connect(self._on_catalog_item_clicked)
        list_layout.addWidget(self.list_view, 1)
        splitter.addWidget(list_card)

        right_panel = QWidget(splitter)
        right_panel.setProperty('pageFamilyHost', True)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._build_selector_card(parent=right_panel), 1)
        right_layout.addWidget(self._build_detail_card(parent=right_panel), 1)
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 58)
        splitter.setStretchFactor(1, 42)
        root.addWidget(splitter, 1)

    def _build_detail_card(self, parent: QWidget | None = None) -> QWidget:
        """Create the hidden detail host and defer the heavy shell until first use."""
        detail_container = QWidget(parent)
        detail_container.setProperty('pageFamilyHost', True)
        detail_container.setMinimumWidth(300)
        self._detail_container_host_layout = QVBoxLayout(detail_container)
        self._detail_container_host_layout.setContentsMargins(0, 0, 0, 0)
        self._detail_container_host_layout.setSpacing(0)
        self.detail_layout = None
        self.detail_card = detail_container
        self.detail_card.setVisible(False)
        return self.detail_card

    def _ensure_detail_card_built(self) -> None:
        if getattr(self, 'detail_layout', None) is not None:
            return
        (
            detail_shell,
            _outer_layout,
            _card,
            _scroll,
            _panel,
            detail_layout,
        ) = build_detail_container_shell(min_width=300, parent=self.detail_card)
        self._detail_container_host_layout.addWidget(detail_shell, 1)
        self.detail_layout = detail_layout

    def _build_selector_card(self, parent: QWidget | None = None):
        selector_card, selector_scroll, selector_panel, selector_layout = build_selector_card_shell(
            spacing=8,
            parent=parent,
        )
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
            title_text=self._t('work_editor.selector.jaws_dialog_title', 'Leukavalitsin'),
            left_badge_text=self._t('work_editor.selector.sp1', 'Pääkara'),
            right_badge_text=self._t('work_editor.jaw.main_spindle_jaws', 'Leuat'),
            fixed_height_policy=True,
            parent=selector_panel,
        )
        selector_layout.addWidget(self.selector_info_header, 0)

        hint = build_selector_hint_label(
            text=self._t('work_editor.selector.action.drag_hint', 'Vedä leuat kirjastosta SP1- tai SP2-paikkaan.'),
            multiline=False,
            parent=selector_panel,
        )
        hint.setProperty('selectorInlineHint', True)
        selector_layout.addWidget(hint, 0)

        self.slot_main = JawAssignmentSlot(
            'main',
            self._t('work_editor.selector.slot.main_jaw', 'SP1-leuka'),
            translate=self._t,
        )
        self.slot_sub = JawAssignmentSlot(
            'sub',
            self._t('work_editor.selector.slot.sub_jaw', 'SP2-leuka'),
            translate=self._t,
        )
        self.slot_main.setMinimumHeight(70)
        self.slot_sub.setMinimumHeight(70)
        self.slot_main.set_drop_placeholder_text(self._t('work_editor.selector.action.drop_hint', 'Pudota leuka tähän'))
        self.slot_sub.set_drop_placeholder_text(self._t('work_editor.selector.action.drop_hint', 'Pudota leuka tähän'))
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
            self._t('work_editor.selector.action.remove', 'Poista'),
            danger=True,
        )
        self.remove_btn.clicked.connect(self._remove_selected)
        self.remove_btn.jawsDropped.connect(self._remove_by_ids)

        actions = build_selector_actions_row(spacing=4)
        actions.addWidget(self.remove_btn, 0, Qt.AlignLeft)
        actions.addStretch(1)

        actions_host = QWidget(selector_card)
        actions_host.setObjectName('jawSelectorActionsHost')
        actions_host.setProperty('selectorActionBar', True)
        actions_host.setProperty('hostTransparent', True)
        actions_host_layout = QHBoxLayout(actions_host)
        actions_host_layout.setContentsMargins(8, 6, 8, 6)
        actions_host_layout.setSpacing(0)
        actions_host_layout.addLayout(actions)

        selector_card_layout.addWidget(selector_scroll, 1)
        selector_card_layout.addWidget(actions_host, 0)
        return selector_card

    def _build_bottom_bar(self, root: QVBoxLayout) -> None:
        build_selector_bottom_bar(
            root,
            translate=self._translate,
            on_cancel=self._cancel,
            on_done=self._send_selector_selection,
            parent=self,
        )

    def _initialize_preview_infrastructure(self) -> None:
        """No-op: preview infrastructure is now warmed up in the Library process.

        SM's process must never create a QWebEngineView (causes D3D11 freeze).
        The Library standalone selector dialog handles 3D preview natively.
        """
        pass

