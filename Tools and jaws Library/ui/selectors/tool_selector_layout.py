from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

try:
    from ...config import ALL_TOOL_TYPES, TOOL_ICONS_DIR
except ImportError:
    from config import ALL_TOOL_TYPES, TOOL_ICONS_DIR
from shared.ui.helpers.editor_helpers import (
    create_titled_section,
    style_icon_action_button,
    style_move_arrow_button,
    style_panel_action_button,
)
from shared.ui.helpers.icon_loader import icon_from_path
from shared.ui.helpers.page_scaffold_common import (
    apply_catalog_list_view_defaults,
    build_catalog_list_shell,
    build_detail_container_shell,
)
from shared.services.tool_lib_profile_view import ToolLibProfileView
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
from ..home_page_support.catalog_list_widgets import ToolCatalogListView
from ..home_page_support.selector_widgets import (
    ToolAssignmentListWidget,
    ToolSelectorRemoveDropButton,
)
from ..shared.selector_panel_builders import (
    build_selector_actions_row,
    build_selector_card_shell,
    build_selector_hint_label,
    build_selector_info_header,
    style_selector_context_button,
)
from .common import build_selector_bottom_bar
from ..tool_catalog_delegate import ToolCatalogDelegate


class ToolSelectorLayoutMixin:

    def _selector_is_machining_center(self) -> bool:
        profile: ToolLibProfileView | None = getattr(self, 'machine_profile', None)
        if profile is None:
            return False
        checker = getattr(profile, 'is_machining_center', None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:
                return False
        return str(getattr(profile, 'machine_type', '') or '').strip().lower() == 'machining_center'

    def _build_toolbar(self, root: QVBoxLayout) -> None:
        """Build the shared filter toolbar matching the library style."""
        frame, self._filter_layout = build_filter_frame()
        # Dialog has no left rail — clear the page-specific objectName and margins
        frame.setObjectName('')
        self._filter_layout.setContentsMargins(8, 6, 8, 6)

        search_icon = icon_from_path(TOOL_ICONS_DIR / 'search_icon.svg', size=QSize(28, 28))
        self._close_icon = icon_from_path(TOOL_ICONS_DIR / 'close_icon.svg', size=QSize(20, 20))

        self.search_toggle = build_search_toggle(search_icon, self._toggle_search)

        # Details toggle → switches right panel between selector and tool details
        self.toggle_details_btn = build_details_toggle(TOOL_ICONS_DIR, self._toggle_detail_panel)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            self._t(
                'work_editor.tool_picker.search_placeholder',
                'Hae työkalun ID:tä, nimeä, mittoja, pidintä, inserttiä tai huomioita...',
            )
        )
        self.search_input.textChanged.connect(self._refresh_catalog)
        self.search_input.setVisible(False)

        self.filter_icon = build_filter_reset(TOOL_ICONS_DIR, self._clear_search)

        self.type_filter = QComboBox()
        self.type_filter.setObjectName('topTypeFilter')
        self.type_filter.addItem(self._t('work_editor.tool_picker.all_types', 'Kaikki tyypit'), 'All')
        for tool_type in ALL_TOOL_TYPES:
            self.type_filter.addItem(tool_type, tool_type)
        self.type_filter.currentIndexChanged.connect(self._refresh_catalog)
        apply_shared_dropdown_style(self.type_filter)

        # Preview toggle: hidden by default — no detached window in selector yet
        self.preview_window_btn = build_preview_toggle(
            TOOL_ICONS_DIR,
            self._t('tool_library.preview.toggle', 'Näytä irrotettava 3D-esikatselu'),
            self.toggle_preview_window,
        )
        self.preview_window_btn.setVisible(True)

        # Right-side detail header: shows "Tool details" + ✕ when detail panel is active
        self.detail_header_container, self.detail_section_label, self.detail_close_btn = \
            build_detail_header(
                self._close_icon,
                self._t('work_editor.selector.assignment.details_title', 'Työkalun tiedot'),
                self._switch_to_selector_panel,
            )
        self.detail_header_container.setVisible(False)

        rebuild_filter_row(
            self._filter_layout,
            self.search_toggle,
            self.toggle_details_btn,
            self.search_input,
            self.filter_icon,
            [self.type_filter],
            self.preview_window_btn,
            self.detail_header_container,
        )

        root.addWidget(frame, 0)

    # Keep old name as alias so the dialog __init__ still calls _build_filter_row
    def _build_filter_row(self, root: QVBoxLayout) -> None:
        self._build_toolbar(root)

    def _build_content(self, root: QVBoxLayout) -> None:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)

        list_card, list_layout = build_catalog_list_shell()
        self.list_view = ToolCatalogListView()
        apply_catalog_list_view_defaults(self.list_view)
        self._model = QStandardItemModel(self.list_view)
        self.list_view.setModel(self._model)
        self.list_view.setItemDelegate(
            ToolCatalogDelegate(parent=self.list_view, view_mode='home', translate=self._t)
        )
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

    def _build_selector_card(self) -> QWidget:
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
            self.selector_head_value_label,
        ) = build_selector_info_header(
            title_text=self._t('work_editor.selector.tools_dialog_title', 'Työkaluvalitsin'),
            left_badge_text=f"{self._t('work_editor.selector.sp1', 'Pääkara')} / {self._t('work_editor.selector.sp2', 'Vastakara')}",
            right_badge_text=self._t('work_editor.selector.head1', 'Yläkara'),
            fixed_height_policy=True,
        )
        self._is_machining_center_selector_mode = self._selector_is_machining_center()
        if self._is_machining_center_selector_mode:
            self.selector_spindle_value_label.setVisible(False)
            self.selector_head_value_label.setVisible(False)
        selector_layout.addWidget(self.selector_info_header, 0)

        context_row = QHBoxLayout()
        context_row.setContentsMargins(0, 0, 0, 0)
        context_row.setSpacing(10)
        context_row.addStretch(1)

        self.head_btn = QPushButton(self._t('work_editor.selector.head1', 'Yläkara'))
        style_selector_context_button(self.head_btn)
        self.head_btn.setMinimumWidth(280)
        self.head_btn.setMaximumWidth(420)
        self.head_btn.clicked.connect(self._toggle_head)
        context_row.addWidget(self.head_btn, 0)
        context_row.addStretch(1)
        if self._is_machining_center_selector_mode:
            self.head_btn.setVisible(False)
            context_row.setSpacing(0)
        selector_layout.addLayout(context_row, 0)

        self.assignment_lists: dict[str, ToolAssignmentListWidget] = {}
        self.assignment_frames: dict[str, QWidget] = {}
        self.assignment_hints: dict[str, QLabel] = {}
        for spindle in ('main', 'sub'):
            assignment_list = ToolAssignmentListWidget()
            assignment_list.setObjectName('toolIdsOrderList')
            assignment_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            assignment_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            assignment_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            assignment_list.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
            assignment_list.setProperty('selectorAssignmentList', True)
            assignment_list.setViewportMargins(0, 0, 2, 0)
            assignment_list.externalToolsDropped.connect(
                lambda dropped, row, target_spindle=spindle: self._on_tools_dropped_for_spindle(target_spindle, dropped, row)
            )
            assignment_list.orderChanged.connect(
                lambda target_spindle=spindle: self._sync_assignment_order_for_spindle(target_spindle)
            )
            assignment_list.itemSelectionChanged.connect(
                lambda target_spindle=spindle: self._on_assignment_selection_changed(target_spindle)
            )

            assignment_frame = create_titled_section(
                self._t('work_editor.tools.sub_spindle_tools', 'Vastakaran työkalut')
                if spindle == 'sub'
                else self._t('work_editor.tools.main_spindle_tools', 'Pääkaran työkalut')
            )
            assignment_frame.setProperty('selectorAssignmentsFrame', True)
            assignment_frame.setProperty('toolIdsPanel', True)
            assignment_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            assignment_layout = QVBoxLayout(assignment_frame)
            assignment_layout.setContentsMargins(8, 10, 8, 8)
            assignment_layout.setSpacing(4)
            assignment_layout.addWidget(assignment_list, 0, Qt.AlignTop)

            empty_hint = build_selector_hint_label(
                text=self._t(
                    'work_editor.selector.action.drag_hint',
                    'Vedä työkalut tähän kirjastosta. Järjestä ne uudelleen vetämällä listassa.',
                ),
                multiline=True,
            )
            empty_hint.setProperty('detailHint', True)
            empty_hint.setProperty('selectorInlineHint', True)
            empty_hint.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            empty_hint.setWordWrap(True)
            empty_hint.setContentsMargins(2, 0, 2, 0)
            assignment_layout.addWidget(empty_hint, 0, Qt.AlignTop)

            selector_layout.addWidget(assignment_frame, 0, Qt.AlignTop)

            self.assignment_lists[spindle] = assignment_list
            self.assignment_frames[spindle] = assignment_frame
            self.assignment_hints[spindle] = empty_hint

        # Compatibility alias for existing call sites that still read assignment_list/frame.
        self.assignment_list = self.assignment_lists['main']
        self.assignment_frame = self.assignment_frames['main']
        selector_layout.addStretch(1)

        actions = build_selector_actions_row(spacing=4)

        self.move_up_btn = QPushButton('▲')
        style_move_arrow_button(self.move_up_btn, '▲', self._t('work_editor.selector.action.move_up', 'Siirrä ylös'))
        self.move_up_btn.clicked.connect(self._move_up)
        actions.addWidget(self.move_up_btn)

        self.move_down_btn = QPushButton('▼')
        style_move_arrow_button(self.move_down_btn, '▼', self._t('work_editor.selector.action.move_down', 'Siirrä alas'))
        self.move_down_btn.clicked.connect(self._move_down)
        actions.addWidget(self.move_down_btn)

        self.remove_btn = ToolSelectorRemoveDropButton()
        style_icon_action_button(self.remove_btn, TOOL_ICONS_DIR / 'delete.svg', self._t('work_editor.selector.action.remove', 'Poista'), danger=True)
        self.remove_btn.clicked.connect(self._remove_selected)
        self.remove_btn.toolsDropped.connect(self._remove_by_drop)
        actions.addWidget(self.remove_btn)

        self.comment_btn = QPushButton()
        style_icon_action_button(self.comment_btn, TOOL_ICONS_DIR / 'comment.svg', self._t('tool_library.selector.add_comment', 'Lisää kommentti'))
        self.comment_btn.clicked.connect(self._add_comment)
        actions.addWidget(self.comment_btn)

        self.delete_comment_btn = QPushButton()
        style_icon_action_button(self.delete_comment_btn, TOOL_ICONS_DIR / 'comment_disable.svg', self._t('tool_library.selector.delete_comment', 'Poista kommentti'))
        self.delete_comment_btn.clicked.connect(self._delete_comment)
        actions.addWidget(self.delete_comment_btn)

        actions_host = QWidget()
        actions_host_layout = QHBoxLayout(actions_host)
        actions_host_layout.setContentsMargins(8, 6, 8, 6)
        actions_host_layout.setSpacing(0)
        actions_host_layout.addStretch(1)
        actions_host_layout.addLayout(actions)
        actions_host_layout.addStretch(1)

        selector_scroll.setWidget(selector_panel)
        scroll_frame = QFrame()
        scroll_frame.setProperty('selectorScrollFrame', True)
        scroll_frame_layout = QVBoxLayout(scroll_frame)
        scroll_frame_layout.setContentsMargins(1, 1, 1, 1)
        scroll_frame_layout.setSpacing(0)
        scroll_frame_layout.addWidget(selector_scroll, 1)

        selector_card_layout.addWidget(scroll_frame, 1)
        selector_card_layout.addWidget(actions_host, 0)
        return selector_card

    def _build_bottom_bar(self, root: QVBoxLayout) -> None:
        build_selector_bottom_bar(
            root,
            translate=self._translate,
            on_cancel=self._cancel,
            on_done=self._send_selector_selection,
        )
