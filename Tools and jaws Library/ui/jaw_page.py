import json
import sqlite3
from pathlib import Path

from typing import Callable

from PySide6.QtCore import QEvent, QModelIndex, QPoint, QSize, Qt, QMimeData, Signal, QTimer
from PySide6.QtGui import QColor, QDrag, QIcon, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import TOOL_ICONS_DIR, SHARED_UI_PREFERENCES_PATH, PROJECTS_DIR
from ui.jaw_catalog_delegate import JawCatalogDelegate, ROLE_JAW_DATA, ROLE_JAW_ICON, ROLE_JAW_ID, jaw_icon_for_row
from ui.jaw_editor_dialog import AddEditJawDialog
from shared.ui.helpers.editor_helpers import (
    apply_secondary_button_theme,
    ask_multi_edit_mode,
    build_titled_detail_field,
    build_titled_detail_list_field,
    create_titled_section,
    create_dialog_buttons,
    setup_editor_dialog,
)
from shared.ui.stl_preview import StlPreviewWidget
from ui.widgets.common import add_shadow, apply_shared_dropdown_style
from ui.selector_mime import SELECTOR_JAW_MIME, encode_selector_payload
from ui.selector_ui_helpers import normalize_selector_spindle, selector_spindle_label
from ui.jaw_page_support import (
    SelectorSlotController,
    JawAssignmentSlot,
    SelectorRemoveDropButton,
    apply_detached_measurement_state as _apply_detached_measurement_state_fn,
    apply_detached_preview_default_bounds as _apply_detached_preview_default_bounds_fn,
    apply_jaw_detail_grid_rules,
    batch_edit_jaws as _batch_edit_jaws_fn,
    close_detached_preview as _close_detached_preview_fn,
    ensure_detached_preview_dialog as _ensure_detached_preview_dialog_fn,
    group_edit_jaws as _group_edit_jaws_fn,
    jaw_preview_has_model_payload,
    jaw_preview_label,
    jaw_preview_measurement_overlays,
    jaw_preview_parts_payload,
    jaw_preview_stl_path,
    load_preview_content as _load_preview_content_fn,
    on_detached_measurements_toggled as _on_detached_measurements_toggled_fn,
    on_detached_preview_closed as _on_detached_preview_closed_fn,
    on_selector_cancel,
    on_selector_done,
    on_selector_toggle_clicked,
    prompt_batch_cancel_behavior as _prompt_batch_cancel_behavior_fn,
    selector_drag_payload_jaw_ids,
    selector_remove_btn_contains_global_point,
    set_preview_button_checked as _set_preview_button_checked_fn,
    sync_detached_preview as _sync_detached_preview_fn,
    toggle_preview_window as _toggle_preview_window_fn,
    update_detached_measurement_toggle_icon as _update_detached_measurement_toggle_icon_fn,
    update_selector_remove_button,
)
from ui.shared.selector_panel_builders import (
    apply_selector_icon_button,
    build_selector_actions_row,
    build_selector_card_shell,
    build_selector_info_header,
    build_selector_hint_label,
    build_selector_toggle_button,
)


class _JawCatalogListView(QListView):
    def startDrag(self, supportedActions):
        selection_model = self.selectionModel()
        if selection_model is None:
            return
        indexes = sorted(selection_model.selectedRows(), key=lambda idx: idx.row())
        if not indexes:
            current = self.currentIndex()
            if current.isValid():
                indexes = [current]
        if not indexes:
            return

        payload: list[dict] = []
        for index in indexes:
            jaw_id = str(index.data(ROLE_JAW_ID) or '').strip()
            if not jaw_id:
                continue
            jaw_data = index.data(ROLE_JAW_DATA) or {}
            payload.append(
                {
                    'jaw_id': jaw_id,
                    'jaw_type': str(jaw_data.get('jaw_type') if isinstance(jaw_data, dict) else '').strip(),
                    'spindle_side': str(jaw_data.get('spindle_side') if isinstance(jaw_data, dict) else '').strip(),
                }
            )
        if not payload:
            return
        mime = QMimeData()
        encode_selector_payload(mime, SELECTOR_JAW_MIME, payload)
        drag = QDrag(self)
        drag.setMimeData(mime)

        # Build a semi-transparent ghost card showing the first jaw
        first = payload[0]
        ghost_text = first.get('jaw_id', '')
        jaw_type = first.get('jaw_type', '')
        if jaw_type:
            ghost_text = f'{ghost_text} - {jaw_type}'
        if len(payload) > 1:
            ghost_text += f'  (+{len(payload) - 1})'
        from PySide6.QtGui import QFont, QPainter
        pixmap = QPixmap(220, 40)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setOpacity(0.75)
        painter.setBrush(QColor('#f0f6fc'))
        painter.setPen(QColor('#637282'))
        painter.drawRoundedRect(1, 1, 218, 38, 6, 6)
        painter.setOpacity(1.0)
        painter.setPen(QColor('#22303c'))
        font = QFont()
        font.setPointSizeF(9.0)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.drawText(10, 4, 200, 32, Qt.AlignVCenter | Qt.TextSingleLine, ghost_text)
        painter.end()
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())

        drag.exec(Qt.CopyAction)


def _lookup_setup_db_used_in_works(jaw_id: str) -> str:
    """Return pipe-separated drawing IDs of Setup Manager works that use jaw_id."""
    if not jaw_id:
        return ''
    # Resolve Setup Manager DB path from shared preferences, then fall back to defaults.
    db_path: Path | None = None
    try:
        if SHARED_UI_PREFERENCES_PATH.exists():
            prefs = json.loads(SHARED_UI_PREFERENCES_PATH.read_text(encoding='utf-8'))
            candidate = str((prefs or {}).get('setup_db_path', '') or '').strip()
            if candidate:
                db_path = Path(candidate)
    except Exception:
        pass
    if db_path is None or not db_path.exists():
        # Fallback: sibling 'Setup Manager/databases/setup_manager.db'
        db_path = PROJECTS_DIR / 'Setup Manager' / 'databases' / 'setup_manager.db'
    if not db_path.exists():
        return ''
    try:
        uri = f'file:{db_path.as_posix()}?mode=ro&immutable=1'
        conn = sqlite3.connect(uri, uri=True)
        rows = conn.execute(
            'SELECT DISTINCT drawing_id FROM works '
            'WHERE (main_jaw_id = ? OR sub_jaw_id = ?) AND drawing_id != ""',
            (jaw_id, jaw_id),
        ).fetchall()
        conn.close()
        return ' | '.join(r[0] for r in rows if r[0])
    except Exception:
        return ''


class JawPage(QWidget):
    NAV_MODES = [
        ('all', 'all'),
        ('main', 'main'),
        ('sub', 'sub'),
        ('soft', 'soft'),
        ('hard_group', 'hard_group'),
    ]

    def __init__(
        self,
        jaw_service,
        parent=None,
        show_sidebar: bool = True,
        translate: Callable[[str, str | None], str] | None = None,
    ):
        super().__init__(parent)
        self.jaw_service = jaw_service
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self.show_sidebar = show_sidebar
        self.current_jaw_id = None
        self.current_view_mode = 'all'
        self._details_hidden = True
        self._last_splitter_sizes = None
        self._module_switch_callback = None
        self._master_filter_ids: set[str] = set()
        self._master_filter_active = False
        self._type_filter_values = ['all', 'soft', 'hard_group', 'special']
        self._selector_active = False
        self._selector_spindle = ''
        self._selector_panel_mode = 'details'
        self._selector_assignments: dict[str, dict | None] = {'main': None, 'sub': None}
        self._selector_selected_slots: set[str] = set()
        self._selector_saved_details_hidden = True
        self._selector_slot_controller = SelectorSlotController(self)
        self._detail_preview_widget = None
        self._detail_preview_model_key = None
        self._detached_preview_dialog = None
        self._detached_preview_widget = None
        self._detached_preview_last_model_key = None
        self._detached_measurements_enabled = True
        self._measurement_toggle_btn = None
        self._close_preview_shortcut = None
        self._build_ui()
        self.refresh_list()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _localized_jaw_type(self, raw_type: str) -> str:
        normalized = (raw_type or '').strip().lower().replace(' ', '_')
        return self._t(f'jaw_library.jaw_type.{normalized}', raw_type)

    def _localized_spindle_side(self, raw_side: str) -> str:
        normalized = (raw_side or '').strip().lower().replace(' ', '_')
        return self._t(f'jaw_library.spindle_side.{normalized}', raw_side)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        filter_frame = self._build_top_filter_frame()
        root.addWidget(filter_frame)

        content = self._build_main_content_layout()
        root.addLayout(content, 1)

        self._build_primary_bottom_bar(root)
        self._build_selector_bottom_bar(root)

        self._set_view_mode('all', refresh=False)
        self._selector_slot_controller.refresh_selector_slots()
        update_selector_remove_button(self)

        self._install_layout_event_filters(filter_frame)

    def _build_top_filter_frame(self) -> QFrame:
        filter_frame = QFrame()
        self.filter_frame = filter_frame
        filter_frame.setObjectName('filterFrame')
        filter_frame.setProperty('card', True)
        self.filter_layout = QHBoxLayout(filter_frame)
        self.filter_layout.setContentsMargins(56, 6, 0, 6)
        self.filter_layout.setSpacing(4)

        self.toolbar_title_label = QLabel(self._t('tool_library.rail_title.jaws', 'Jaws Library'))
        self.toolbar_title_label.setProperty('pageTitle', True)
        self.toolbar_title_label.setStyleSheet('padding-left: 0px; padding-right: 20px;')

        self.search_toggle = QToolButton()
        self.search_icon = QIcon(str(TOOL_ICONS_DIR / 'search_icon.svg'))
        self.close_icon = QIcon(str(TOOL_ICONS_DIR / 'close_icon.svg'))
        self.search_toggle.setIcon(self.search_icon)
        self.search_toggle.setIconSize(QSize(28, 28))
        self.search_toggle.setCheckable(True)
        self.search_toggle.setAutoRaise(True)
        self.search_toggle.setProperty('topBarIconButton', True)
        self.search_toggle.setFixedSize(36, 36)
        self.search_toggle.clicked.connect(self._toggle_search)

        self.search = QLineEdit()
        self.search.setPlaceholderText(
            self._t('jaw_library.search.placeholder', 'Search jaw ID, type, spindle, diameter, work, washer or notes')
        )
        self.search.setVisible(False)
        self.search.textChanged.connect(self.refresh_list)

        self.toggle_details_btn = QToolButton()
        self.toggle_details_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / 'tooltip.svg')))
        self.toggle_details_btn.setIconSize(QSize(28, 28))
        self.toggle_details_btn.setAutoRaise(True)
        self.toggle_details_btn.setProperty('topBarIconButton', True)
        self.toggle_details_btn.setProperty('secondaryAction', True)
        self.toggle_details_btn.setFixedSize(36, 36)
        self.toggle_details_btn.clicked.connect(self.toggle_details)

        self.detail_header_container = QWidget()
        detail_top = QHBoxLayout(self.detail_header_container)
        detail_top.setContentsMargins(0, 0, 0, 0)
        detail_top.setSpacing(6)
        self.detail_section_label = QLabel(self._t('jaw_library.section.details', 'Jaw details'))
        self.detail_section_label.setProperty('detailSectionTitle', True)
        self.detail_section_label.setStyleSheet('padding: 0 2px 0 0; font-size: 18px;')
        detail_top.addWidget(self.detail_section_label)
        detail_top.addStretch(1)

        self.detail_close_btn = QToolButton()
        self.detail_close_btn.setIcon(self.close_icon)
        self.detail_close_btn.setIconSize(QSize(20, 20))
        self.detail_close_btn.setAutoRaise(True)
        self.detail_close_btn.setProperty('topBarIconButton', True)
        self.detail_close_btn.setFixedSize(32, 32)
        self.detail_close_btn.clicked.connect(self.hide_details)
        detail_top.addWidget(self.detail_close_btn)

        self.filter_icon = QToolButton()
        self.filter_icon.setIcon(QIcon(str(TOOL_ICONS_DIR / 'filter_arrow_right.svg')))
        self.filter_icon.setIconSize(QSize(28, 28))
        self.filter_icon.setAutoRaise(True)
        self.filter_icon.setProperty('topBarIconButton', True)
        self.filter_icon.setFixedSize(36, 36)
        self.filter_icon.clicked.connect(self._clear_type_filter)

        self.jaw_type_filter = QComboBox()
        self.jaw_type_filter.setObjectName('topTypeFilter')
        self._build_type_filter_items()
        self.jaw_type_filter.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.jaw_type_filter.setMinimumWidth(60)
        self.jaw_type_filter.currentIndexChanged.connect(self._on_type_filter_changed)
        add_shadow(self.jaw_type_filter)
        apply_shared_dropdown_style(self.jaw_type_filter)
        self.jaw_type_filter.installEventFilter(self)
        self.jaw_type_filter.view().installEventFilter(self)

        self.preview_window_btn = QToolButton()
        self.preview_window_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / '3d_icon.svg')))
        self.preview_window_btn.setIconSize(QSize(28, 28))
        self.preview_window_btn.setCheckable(True)
        self.preview_window_btn.setAutoRaise(True)
        self.preview_window_btn.setProperty('topBarIconButton', True)
        self.preview_window_btn.setToolTip(self._t('tool_library.preview.toggle', 'Toggle detached 3D preview'))
        self.preview_window_btn.setFixedSize(36, 36)
        self.preview_window_btn.clicked.connect(self.toggle_preview_window)

        self._rebuild_filter_row()
        return filter_frame

    def _build_main_content_layout(self) -> QHBoxLayout:
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(10)

        self.view_buttons = []
        if self.show_sidebar:
            self.sidebar = QFrame()
            self.sidebar.setProperty('card', True)
            self.sidebar.setFixedWidth(188)
            side_layout = QVBoxLayout(self.sidebar)
            side_layout.setContentsMargins(10, 12, 10, 12)
            side_layout.setSpacing(6)

            side_title = QLabel(self._t('jaw_library.section.views', 'Jaw Views'))
            side_title.setProperty('detailSectionTitle', True)
            side_layout.addWidget(side_title)

            for _title, mode in self.NAV_MODES:
                btn = QPushButton(self._nav_mode_title(mode))
                btn.setProperty('panelActionButton', True)
                btn.clicked.connect(lambda _checked=False, m=mode: self._set_view_mode(m))
                side_layout.addWidget(btn)
                self.view_buttons.append((mode, btn))
            side_layout.addStretch(1)
            content.addWidget(self.sidebar, 0)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self._build_catalog_list_card())
        self.splitter.addWidget(self._build_detail_container())

        content.addWidget(self.splitter, 1)
        return content

    def _build_catalog_list_card(self) -> QFrame:
        list_card = QFrame()
        list_card.setProperty('catalogShell', True)
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(10)

        self.jaw_list = _JawCatalogListView()
        self.jaw_list.setObjectName('toolCatalog')
        self.jaw_list.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.jaw_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.jaw_list.setSelectionMode(QListView.ExtendedSelection)
        self.jaw_list.setDragEnabled(True)
        self.jaw_list.setMouseTracking(True)
        self.jaw_list.setStyleSheet(
            "QListView#toolCatalog { border: none; outline: none; padding: 8px; }"
            " QListView#toolCatalog::item { background: transparent; border: none; }"
        )
        self.jaw_list.setSpacing(4)
        self._jaw_model = QStandardItemModel(self)
        self.jaw_list.setModel(self._jaw_model)
        self._jaw_delegate = JawCatalogDelegate(parent=self.jaw_list, translate=self._t)
        self.jaw_list.setItemDelegate(self._jaw_delegate)
        self.jaw_list.installEventFilter(self)
        self.jaw_list.viewport().installEventFilter(self)
        self.jaw_list.selectionModel().currentChanged.connect(self.on_current_item_changed)
        self.jaw_list.selectionModel().selectionChanged.connect(self._on_multi_selection_changed)
        self.jaw_list.doubleClicked.connect(self.on_item_double_clicked)
        list_layout.addWidget(self.jaw_list, 1)
        return list_card

    def _build_detail_container(self) -> QWidget:
        self.detail_container = QWidget()
        self.detail_container.setMinimumWidth(280)
        detail_layout = QVBoxLayout(self.detail_container)
        self._detail_container_layout = detail_layout
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(0)

        self.detail_card = QFrame()
        self.detail_card.setProperty('card', True)
        detail_card_layout = QVBoxLayout(self.detail_card)
        detail_card_layout.setContentsMargins(0, 0, 0, 0)
        detail_card_layout.setSpacing(0)

        self.detail_scroll = QScrollArea()
        self.detail_scroll.setObjectName('detailScrollArea')
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.NoFrame)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.detail_panel = QWidget()
        self.detail_panel.setObjectName('detailPanel')
        self.detail_layout = QVBoxLayout(self.detail_panel)
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_layout.setSpacing(10)
        self.detail_scroll.setWidget(self.detail_panel)
        self.populate_details(None)

        detail_card_layout.addWidget(self.detail_scroll, 1)
        detail_layout.addWidget(self.detail_card, 1)
        detail_layout.addWidget(self._build_selector_card(), 1)

        self.detail_container.hide()
        self.detail_header_container.hide()
        self.splitter.setSizes([1, 0])
        return self.detail_container

    def _build_selector_card(self) -> QFrame:
        self.selector_card, self.selector_scroll, self.selector_panel, selector_layout = build_selector_card_shell(spacing=8)
        selector_card_layout = QVBoxLayout(self.selector_card)
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
        )
        selector_layout.addWidget(self.selector_info_header, 0)

        ctx_row = QHBoxLayout()
        ctx_row.setContentsMargins(0, 0, 0, 0)
        ctx_row.setSpacing(10)
        ctx_row.addStretch(1)

        self.selector_toggle_btn = build_selector_toggle_button(
            text=self._t('tool_library.selector.mode_details', 'DETAILS'),
            on_clicked=lambda: on_selector_toggle_clicked(self),
        )
        ctx_row.addWidget(self.selector_toggle_btn, 0)
        ctx_row.addStretch(1)
        selector_layout.addLayout(ctx_row)

        self.selector_hint_label = build_selector_hint_label(
            text=self._t('tool_library.selector.jaw_hint', 'Drag jaws from the catalog to SP1 or SP2.'),
            multiline=True,
        )
        selector_layout.addWidget(self.selector_hint_label, 0)

        self.selector_sp1_slot = JawAssignmentSlot('main', self._t('jaw_library.selector.sp1_slot', 'SP1 jaw'))
        self.selector_sp2_slot = JawAssignmentSlot('sub', self._t('jaw_library.selector.sp2_slot', 'SP2 jaw'))
        self.selector_sp1_slot.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.selector_sp2_slot.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.selector_sp1_slot.set_drop_placeholder_text(self._t('jaw_library.selector.drop_here', 'Drop jaw here'))
        self.selector_sp2_slot.set_drop_placeholder_text(self._t('jaw_library.selector.drop_here', 'Drop jaw here'))
        self.selector_sp1_slot.jawDropped.connect(self._selector_slot_controller.on_selector_jaw_dropped)
        self.selector_sp2_slot.jawDropped.connect(self._selector_slot_controller.on_selector_jaw_dropped)
        self.selector_sp1_slot.slotClicked.connect(self._selector_slot_controller.on_selector_slot_clicked)
        self.selector_sp2_slot.slotClicked.connect(self._selector_slot_controller.on_selector_slot_clicked)
        selector_layout.addWidget(self.selector_sp1_slot, 0)
        selector_layout.addWidget(self.selector_sp2_slot, 0)
        selector_layout.addStretch(1)

        self.selector_remove_btn = SelectorRemoveDropButton()
        apply_selector_icon_button(
            self.selector_remove_btn,
            icon_path=TOOL_ICONS_DIR / 'delete.svg',
            tooltip=self._t('tool_library.selector.remove', 'Remove'),
            danger=True,
        )
        self.selector_remove_btn.clicked.connect(self._selector_slot_controller.remove_selected_selector_jaws)
        self.selector_remove_btn.jawsDropped.connect(self._selector_slot_controller.remove_selector_jaws_by_ids)
        selector_actions = build_selector_actions_row(spacing=4)
        selector_actions.addWidget(self.selector_remove_btn, 0, Qt.AlignLeft)
        selector_actions.addStretch(1)
        selector_layout.addLayout(selector_actions)

        self.selector_scroll.setWidget(self.selector_panel)
        selector_card_layout.addWidget(self.selector_scroll, 1)
        return self.selector_card

    def _build_primary_bottom_bar(self, root: QVBoxLayout) -> None:
        self.button_bar = QFrame()
        self.button_bar.setProperty('bottomBar', True)
        actions = QHBoxLayout(self.button_bar)
        actions.setContentsMargins(10, 8, 10, 8)
        actions.setSpacing(8)

        self.edit_btn = QPushButton(self._t('jaw_library.action.edit_jaw_button', 'EDIT JAW'))
        self.delete_btn = QPushButton(self._t('jaw_library.action.delete_jaw_button', 'DELETE JAW'))
        self.add_btn = QPushButton(self._t('jaw_library.action.add_jaw_button', 'ADD JAW'))
        self.copy_btn = QPushButton(self._t('jaw_library.action.copy_jaw_button', 'COPY JAW'))
        for btn in [self.edit_btn, self.delete_btn, self.add_btn, self.copy_btn]:
            btn.setProperty('panelActionButton', True)
        self.delete_btn.setProperty('dangerAction', True)
        self.add_btn.setProperty('primaryAction', True)

        self.edit_btn.clicked.connect(self.edit_jaw)
        self.delete_btn.clicked.connect(self.delete_jaw)
        self.add_btn.clicked.connect(self.add_jaw)
        self.copy_btn.clicked.connect(self.copy_jaw)

        self.module_switch_label = QLabel(self._t('tool_library.module.switch_to', 'Switch to'))
        self.module_switch_label.setProperty('pageSubtitle', True)
        self.module_toggle_btn = QPushButton(self._t('tool_library.module.tools', 'TOOLS'))
        self.module_toggle_btn.setProperty('panelActionButton', True)
        self.module_toggle_btn.setFixedHeight(28)
        self.module_toggle_btn.clicked.connect(
            lambda: self._module_switch_callback() if callable(self._module_switch_callback) else None
        )

        actions.addWidget(self.module_switch_label, 0, Qt.AlignLeft | Qt.AlignVCenter)
        actions.addWidget(self.module_toggle_btn, 0, Qt.AlignLeft | Qt.AlignVCenter)
        actions.addStretch(1)
        self.selection_count_label = QLabel('')
        self.selection_count_label.setProperty('detailHint', True)
        self.selection_count_label.setStyleSheet('background: transparent; border: none;')
        self.selection_count_label.hide()
        actions.addWidget(self.selection_count_label, 0, Qt.AlignBottom)
        actions.addWidget(self.add_btn)
        actions.addWidget(self.edit_btn)
        actions.addWidget(self.delete_btn)
        actions.addWidget(self.copy_btn)
        root.addWidget(self.button_bar)

    def _build_selector_bottom_bar(self, root: QVBoxLayout) -> None:
        self.selector_bottom_bar = QFrame()
        self.selector_bottom_bar.setProperty('bottomBar', True)
        self.selector_bottom_bar.setVisible(False)
        sel_bar_layout = QHBoxLayout(self.selector_bottom_bar)
        sel_bar_layout.setContentsMargins(10, 8, 10, 8)
        sel_bar_layout.setSpacing(8)
        sel_bar_layout.addStretch(1)

        self.selector_cancel_btn = QPushButton(self._t('tool_library.selector.cancel', 'CANCEL'))
        self.selector_cancel_btn.setProperty('panelActionButton', True)
        self.selector_cancel_btn.clicked.connect(lambda: on_selector_cancel(self))
        sel_bar_layout.addWidget(self.selector_cancel_btn)

        self.selector_done_btn = QPushButton(self._t('tool_library.selector.done', 'DONE'))
        self.selector_done_btn.setProperty('panelActionButton', True)
        self.selector_done_btn.setProperty('primaryAction', True)
        self.selector_done_btn.clicked.connect(lambda: on_selector_done(self))
        sel_bar_layout.addWidget(self.selector_done_btn)
        root.addWidget(self.selector_bottom_bar)

    def _install_layout_event_filters(self, filter_frame: QFrame) -> None:
        # Keep wheel and splitter interactions consistent in list/detail/selector modes.
        self.selector_card.installEventFilter(self)
        self.selector_scroll.viewport().installEventFilter(self)
        self.selector_panel.installEventFilter(self)
        self.detail_container.installEventFilter(self)
        self.splitter.installEventFilter(self)
        filter_frame.installEventFilter(self)
        self.button_bar.installEventFilter(self)
        self.selector_bottom_bar.installEventFilter(self)
        self.detail_header_container.installEventFilter(self)

    def set_module_switch_handler(self, callback):
        self._module_switch_callback = callback

    def set_module_switch_target(self, target: str):
        target_text = (target or '').strip().upper() or 'TOOLS'
        display = self._t('tool_library.module.tools', 'TOOLS') if target_text == 'TOOLS' else self._t('tool_library.module.jaws', 'JAWS')
        self.module_toggle_btn.setText(display)
        self.module_toggle_btn.setToolTip(self._t('tool_library.module.switch_to_target', 'Switch to {target} module', target=display))

    def set_master_filter(self, jaw_ids, active: bool):
        self._master_filter_ids = {str(j).strip() for j in (jaw_ids or []) if str(j).strip()}
        self._master_filter_active = bool(active) and bool(self._master_filter_ids)
        self.refresh_list()

    @staticmethod
    def _normalize_selector_spindle(value: str | None) -> str:
        return normalize_selector_spindle(value)

    @staticmethod
    def _selector_spindle_label(spindle: str) -> str:
        return selector_spindle_label(spindle)

    def set_selector_context(
        self,
        active: bool,
        spindle: str = '',
        initial_assignments: list[dict] | None = None,
    ) -> None:
        self._selector_slot_controller.set_selector_context(
            active,
            spindle=spindle,
            initial_assignments=initial_assignments,
        )

    def selector_assigned_jaws_for_setup_assignment(self) -> list[dict]:
        """Return slot assignments with slot key included so Setup Manager can correlate correctly."""
        return self._selector_slot_controller.selector_assigned_jaws_for_setup_assignment()

    def _toggle_search(self):
        show = self.search_toggle.isChecked()
        self.jaw_type_filter.hide()
        self.search.setVisible(show)
        self.search_toggle.setIcon(self.close_icon if show else self.search_icon)
        if not show:
            self.search.clear()
            self.refresh_list()
        self._rebuild_filter_row()
        self.jaw_type_filter.hidePopup()
        self._suppress_combo = True
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: setattr(self, '_suppress_combo', False))
        self.jaw_type_filter.setEnabled(False)
        QTimer.singleShot(0, lambda: self.jaw_type_filter.setEnabled(True))
        self.jaw_type_filter.show()
        if show:
            QTimer.singleShot(0, self.search.setFocus)

    def _set_view_mode(self, mode: str, refresh: bool = True):
        self.current_view_mode = mode
        for btn_mode, btn in self.view_buttons:
            btn.setProperty('primaryAction', btn_mode == mode)
            style = btn.style()
            style.unpolish(btn)
            style.polish(btn)
            btn.update()
        if refresh:
            self.refresh_list()

    def set_view_mode(self, mode: str):
        self._set_view_mode(mode, refresh=True)

    def _nav_mode_title(self, mode: str) -> str:
        mapping = {
            'all': self._t('tool_library.nav.all_jaws', 'All Jaws'),
            'main': self._t('tool_library.nav.main_spindle', 'Main Spindle'),
            'sub': self._t('tool_library.nav.sub_spindle', 'Sub Spindle'),
            'soft': self._t('jaw_library.nav.soft_jaws', 'Soft Jaws'),
            'hard_group': self._t('jaw_library.nav.hard_group', 'Hard / Spiked / Special'),
        }
        return mapping.get(mode, mode)

    def _set_type_filter_value(self, value: str):
        target = (value or 'all').strip()
        for idx in range(self.jaw_type_filter.count()):
            if self.jaw_type_filter.itemData(idx) == target:
                self.jaw_type_filter.setCurrentIndex(idx)
                return
        if self.jaw_type_filter.count():
            self.jaw_type_filter.setCurrentIndex(0)

    def _build_type_filter_items(self):
        if not hasattr(self, 'jaw_type_filter'):
            return
        current = self.jaw_type_filter.currentData() if self.jaw_type_filter.count() else 'all'
        self.jaw_type_filter.blockSignals(True)
        self.jaw_type_filter.clear()
        self.jaw_type_filter.addItem(self._t('jaw_library.filter.all', 'All'), 'all')
        self.jaw_type_filter.addItem(self._t('jaw_library.filter.soft_jaws', 'Soft Jaws'), 'soft')
        self.jaw_type_filter.addItem(self._t('jaw_library.filter.hard_spiked', 'Spike/Hard Jaws'), 'hard_group')
        self.jaw_type_filter.addItem(self._t('jaw_library.filter.special_jaws', 'Special Jaws'), 'special')
        self._set_type_filter_value(current if current in self._type_filter_values else 'all')
        self.jaw_type_filter.blockSignals(False)

    def _rebuild_filter_row(self):
        while self.filter_layout.count():
            item = self.filter_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        self.filter_layout.addWidget(self.search_toggle)
        self.filter_layout.addWidget(self.toggle_details_btn)
        if self.search.isVisible():
            self.filter_layout.addWidget(self.search, 1)
        self.filter_layout.addWidget(self.filter_icon)
        self.filter_layout.addWidget(self.jaw_type_filter)
        self.filter_layout.addWidget(self.preview_window_btn)
        self.filter_layout.addStretch(1)
        self.filter_layout.addWidget(self.detail_header_container)

    def _on_type_filter_changed(self, _index: int):
        active = (self.jaw_type_filter.currentData() or 'all') != 'all'
        icon_name = 'filter_off.svg' if active else 'filter_arrow_right.svg'
        self.filter_icon.setIcon(QIcon(str(TOOL_ICONS_DIR / icon_name)))
        self.refresh_list()

    def _clear_type_filter(self):
        self._set_type_filter_value('all')

    def eventFilter(self, obj, event):
        if obj is getattr(self, 'jaw_type_filter', None) or (
                getattr(self, 'jaw_type_filter', None) and obj is self.jaw_type_filter.view()):
            if getattr(self, '_suppress_combo', False) and event.type() in (QEvent.Show, QEvent.ShowToParent):
                return True
        selector_drag_targets = {
            getattr(self, 'selector_card', None),
            getattr(self, 'selector_panel', None),
            getattr(self, 'selector_scroll', None) and self.selector_scroll.viewport(),
        }
        if (
            self._selector_active
            and obj in selector_drag_targets
            and event.type() in (QEvent.DragEnter, QEvent.DragMove, QEvent.Drop)
            and hasattr(event, 'mimeData')
        ):
            jaw_ids = selector_drag_payload_jaw_ids(self, event.mimeData())
            point = event.position().toPoint() if hasattr(event, 'position') else None
            if jaw_ids and point is not None:
                global_pos = obj.mapToGlobal(point)
                if selector_remove_btn_contains_global_point(self, global_pos):
                    if event.type() == QEvent.Drop:
                        self._selector_slot_controller.remove_selector_jaws_by_ids(jaw_ids)
                    event.acceptProposedAction()
                    return True
        selector_click_targets = {
            getattr(self, 'selector_card', None),
            getattr(self, 'selector_panel', None),
            getattr(self, 'detail_container', None),
            getattr(self, 'splitter', None),
            getattr(self, 'button_bar', None),
            getattr(self, 'selector_bottom_bar', None),
            getattr(self, 'filter_frame', None),
            getattr(self, 'detail_header_container', None),
            getattr(self, 'selector_scroll', None) and self.selector_scroll.viewport(),
        }
        if (
            self._selector_active
            and event.type() == QEvent.MouseButtonPress
            and obj in selector_click_targets
            and hasattr(event, 'pos')
        ):
            global_pos = obj.mapToGlobal(event.pos())
            on_slot = False
            for slot_widget in (getattr(self, 'selector_sp1_slot', None), getattr(self, 'selector_sp2_slot', None)):
                if slot_widget is None:
                    continue
                local_pos = slot_widget.mapFromGlobal(global_pos)
                if slot_widget.rect().contains(local_pos):
                    on_slot = True
                    break
            if not on_slot and hasattr(self, 'selector_remove_btn'):
                remove_local = self.selector_remove_btn.mapFromGlobal(global_pos)
                if self.selector_remove_btn.rect().contains(remove_local):
                    on_slot = True
            if not on_slot and self._selector_selected_slots:
                self._selector_selected_slots.clear()
                self._selector_slot_controller.refresh_selector_slots()
        if obj in (getattr(self, 'jaw_list', None),
                   getattr(self, 'jaw_list', None) and self.jaw_list.viewport()):
            if event.type() == QEvent.MouseButtonPress:
                if not self.jaw_list.indexAt(event.pos()).isValid():
                    self._clear_selection()
        return super().eventFilter(obj, event)

    def _clear_selection(self):
        details_were_open = not self._details_hidden
        if hasattr(self, 'jaw_list'):
            self.jaw_list.selectionModel().clearSelection()
            self.jaw_list.setCurrentIndex(QModelIndex())
        self.current_jaw_id = None
        self._update_selection_count_label()
        self.populate_details(None)
        self._sync_detached_preview(show_errors=False)
        if details_were_open:
            self.hide_details()

    def _selected_jaw_ids(self) -> list[str]:
        model = self.jaw_list.selectionModel()
        if model is None:
            return []
        indexes = sorted(model.selectedIndexes(), key=lambda idx: idx.row())
        jaw_ids: list[str] = []
        for index in indexes:
            jaw_id = (index.data(ROLE_JAW_ID) or '').strip()
            if jaw_id and jaw_id not in jaw_ids:
                jaw_ids.append(jaw_id)
        return jaw_ids

    def selected_jaws_for_setup_assignment(self) -> list[dict]:
        model = self.jaw_list.selectionModel()
        if model is None:
            return []
        indexes = sorted(model.selectedIndexes(), key=lambda idx: idx.row())
        payload: list[dict] = []
        for index in indexes:
            jaw_id = str(index.data(ROLE_JAW_ID) or '').strip()
            jaw_data = index.data(ROLE_JAW_DATA) or {}
            jaw_type = str((jaw_data.get('jaw_type') if isinstance(jaw_data, dict) else None) or '').strip()
            payload.append({
                'jaw_id': jaw_id,
                'jaw_type': jaw_type,
            })
        return payload

    def _on_multi_selection_changed(self, _selected, _deselected):
        self._update_selection_count_label()

    def _update_selection_count_label(self):
        count = len(self._selected_jaw_ids())
        if count > 1:
            self.selection_count_label.setText(
                self._t('jaw_library.selection.count', '{count} selected', count=count)
            )
            self.selection_count_label.show()
            return
        self.selection_count_label.hide()

    def _prompt_batch_cancel_behavior(self) -> str:
        return _prompt_batch_cancel_behavior_fn(self)

    def _batch_edit_jaws(self, jaw_ids: list[str]):
        _batch_edit_jaws_fn(self, jaw_ids)

    def _group_edit_jaws(self, jaw_ids: list[str]):
        _group_edit_jaws_fn(self, jaw_ids)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._clear_selection()
            return
        super().keyPressEvent(event)

    def _clear_details(self):
        self._detail_preview_widget = None
        self._detail_preview_model_key = None
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _split_used_in_works(self, value: str) -> list[str]:
        return [p.strip() for p in (value or '').split('|') if p.strip()]

    @staticmethod
    def _preview_model_key(jaw: dict | None):
        if not isinstance(jaw, dict):
            return None
        jaw_id = str(jaw.get('jaw_id') or '').strip()
        raw_stl = jaw.get('stl_path')
        if isinstance(raw_stl, str):
            stl_key = raw_stl
        else:
            try:
                stl_key = json.dumps(raw_stl, ensure_ascii=False, sort_keys=True)
            except Exception:
                stl_key = str(raw_stl)
        raw_meas = jaw.get('measurement_overlays', [])
        if isinstance(raw_meas, str):
            meas_key = raw_meas
        else:
            try:
                meas_key = json.dumps(raw_meas, ensure_ascii=False, sort_keys=True)
            except Exception:
                meas_key = str(raw_meas)
        return jaw_id, stl_key, meas_key

    def _set_preview_button_checked(self, checked: bool):
        _set_preview_button_checked_fn(self, checked)

    def _load_preview_content(self, viewer: StlPreviewWidget, jaw: dict, *, label: str | None = None) -> bool:
        return _load_preview_content_fn(self, viewer, jaw, label=label)

    def _ensure_detached_preview_dialog(self):
        _ensure_detached_preview_dialog_fn(self)

    def _apply_detached_preview_default_bounds(self):
        _apply_detached_preview_default_bounds_fn(self)

    def _update_detached_measurement_toggle_icon(self, enabled: bool):
        _update_detached_measurement_toggle_icon_fn(self, enabled)

    def _on_detached_measurements_toggled(self, checked: bool):
        _on_detached_measurements_toggled_fn(self, checked)

    def _apply_detached_measurement_state(self, jaw: dict):
        _apply_detached_measurement_state_fn(self, jaw)

    def _on_detached_preview_closed(self, _result):
        _on_detached_preview_closed_fn(self, _result)

    def _close_detached_preview(self):
        _close_detached_preview_fn(self)

    def _sync_detached_preview(self, show_errors: bool = False) -> bool:
        return _sync_detached_preview_fn(self, show_errors)

    def toggle_preview_window(self):
        _toggle_preview_window_fn(self)

    def _build_empty_details_card(self) -> QFrame:
        card = QFrame()
        card.setProperty('subCard', True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        title = QLabel(self._t('jaw_library.section.details', 'Jaw details'))
        title.setProperty('detailSectionTitle', True)
        hint = QLabel(self._t('jaw_library.message.select_jaw_for_details', 'Select a jaw to view details.'))
        hint.setProperty('detailHint', True)
        hint.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(hint)

        placeholder = QFrame()
        placeholder.setProperty('diagramPanel', True)
        placeholder_layout = QVBoxLayout(placeholder)
        placeholder_layout.setContentsMargins(12, 12, 12, 12)
        placeholder_layout.addStretch(1)
        placeholder_layout.addStretch(1)
        layout.addWidget(placeholder)
        return card

    def _build_jaw_detail_header(self, jaw: dict) -> QFrame:
        header = QFrame()
        header.setProperty('detailHeader', True)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 14, 14, 12)
        header_layout.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)
        jaw_id_lbl = QLabel(jaw.get('jaw_id', ''))
        jaw_id_lbl.setProperty('detailHeroTitle', True)
        jaw_id_lbl.setWordWrap(True)
        diam_lbl = QLabel(jaw.get('clamping_diameter_text', '') or '')
        diam_lbl.setProperty('detailHeroTitle', True)
        diam_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        title_row.addWidget(jaw_id_lbl, 1)
        title_row.addWidget(diam_lbl, 0, Qt.AlignRight)

        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge = QLabel(self._localized_jaw_type(jaw.get('jaw_type', '')))
        badge.setProperty('toolBadge', True)
        badge_row.addWidget(badge, 0, Qt.AlignLeft)
        badge_row.addStretch(1)

        header_layout.addLayout(title_row)
        header_layout.addLayout(badge_row)
        return header

    def _build_jaw_preview_card(self, jaw: dict) -> QWidget:
        preview_card = create_titled_section(self._t('tool_library.section.preview', 'Preview'))
        preview_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setSpacing(10)
        preview_layout.setContentsMargins(6, 4, 6, 6)

        diagram = QWidget()
        diagram.setObjectName('detailPreviewGradientHost')
        diagram.setAttribute(Qt.WA_StyledBackground, True)
        diagram.setStyleSheet(
            'QWidget#detailPreviewGradientHost {'
            '  background-color: #d6d9de;'
            '  border: none;'
            '  border-radius: 6px;'
            '}'
        )
        diagram.setMinimumHeight(300)
        diagram.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        diagram_layout = QVBoxLayout(diagram)
        diagram_layout.setContentsMargins(6, 6, 6, 6)
        diagram_layout.setSpacing(0)

        viewer = StlPreviewWidget()
        viewer.setStyleSheet('background: transparent; border: none;')
        viewer.set_control_hint_text(
            self._t(
                'tool_editor.hint.rotate_pan_zoom',
                'Rotate: left mouse â€¢ Pan: right mouse â€¢ Zoom: mouse wheel',
            )
        )

        loaded = self._load_preview_content(viewer, jaw, label=jaw_preview_label(jaw, self._t))
        if loaded:
            viewer.setMinimumHeight(260)
            overlays = jaw_preview_measurement_overlays(jaw)
            viewer.set_measurement_overlays(overlays)
            viewer.set_measurements_visible(bool(overlays))
            diagram_layout.addWidget(viewer, 1)
            self._detail_preview_widget = viewer
            self._detail_preview_model_key = self._preview_model_key(jaw)
        else:
            stl_path = jaw_preview_stl_path(jaw)
            placeholder = QLabel(
                self._t('tool_library.preview.invalid_data', 'No valid 3D model data found.')
                if stl_path
                else self._t('tool_library.preview.none_assigned', 'No 3D model assigned.')
            )
            placeholder.setProperty('detailHint', True)
            placeholder.setWordWrap(True)
            placeholder.setAlignment(Qt.AlignCenter)
            diagram_layout.addStretch(1)
            diagram_layout.addWidget(placeholder)
            diagram_layout.addStretch(1)
            self._detail_preview_widget = None
            self._detail_preview_model_key = None

        preview_layout.addWidget(diagram, 1)
        return preview_card

    def populate_details(self, jaw):
        self._clear_details()

        if not jaw:
            self.detail_layout.addWidget(self._build_empty_details_card())
            self.detail_layout.addStretch(1)
            return

        card = QFrame()
        card.setProperty('subCard', True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(self._build_jaw_detail_header(jaw))

        info = QGridLayout()
        info.setHorizontalSpacing(14)
        info.setVerticalSpacing(8)

        def add_field(row: int, col: int, row_span: int, col_span: int, label_text: str, value_text: str) -> None:
            info.addWidget(
                build_titled_detail_field(label_text, '' if value_text is None else str(value_text)),
                row,
                col,
                row_span,
                col_span,
                Qt.AlignTop,
            )

        next_row = apply_jaw_detail_grid_rules(
            jaw=jaw,
            translate=self._t,
            localized_spindle_side=self._localized_spindle_side(jaw.get('spindle_side', '')),
            add_field=add_field,
        )

        info.addWidget(
            build_titled_detail_list_field(
                self._t('jaw_library.field.used_in_works', 'Used in works:'),
                self._split_used_in_works(_lookup_setup_db_used_in_works(jaw.get('jaw_id', ''))),
            ),
            next_row,
            0,
            1,
            4,
            Qt.AlignTop,
        )

        notes_text = (jaw.get('notes', '') or '').strip()
        if notes_text:
            info.addWidget(
                build_titled_detail_field(
                    self._t('jaw_library.field.notes', 'Notes'),
                    notes_text,
                    multiline=True,
                ),
                next_row + 1,
                0,
                1,
                4,
                Qt.AlignTop,
            )

        layout.addLayout(info)
        layout.addWidget(self._build_jaw_preview_card(jaw))
        layout.addStretch(1)
        self.detail_layout.addWidget(card)
        self._sync_detached_preview(show_errors=False)

    def select_jaw_by_id(self, jaw_id: str):
        """Navigate the list to the jaw with the given jaw_id."""
        self.current_jaw_id = jaw_id.strip()
        self.refresh_list()
        for row in range(self._jaw_model.rowCount()):
            idx = self._jaw_model.index(row, 0)
            if idx.data(ROLE_JAW_ID) == self.current_jaw_id:
                self.jaw_list.setCurrentIndex(idx)
                self.jaw_list.scrollTo(idx)
                break

    def refresh_list(self):
        type_filter = self.jaw_type_filter.currentData() if hasattr(self, 'jaw_type_filter') else 'all'
        jaws = self.jaw_service.list_jaws(self.search.text(), self.current_view_mode, type_filter)
        if self._master_filter_active:
            jaws = [jaw for jaw in jaws if str(jaw.get('jaw_id', '')).strip() in self._master_filter_ids]
        self._jaw_model.blockSignals(True)
        self._jaw_model.clear()
        for jaw in jaws:
            item = QStandardItem()
            jaw_id = jaw.get('jaw_id', '')
            item.setData(jaw_id, ROLE_JAW_ID)
            item.setData(jaw, ROLE_JAW_DATA)
            item.setData(jaw_icon_for_row(jaw), ROLE_JAW_ICON)
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
            self._jaw_model.appendRow(item)
        self._jaw_model.blockSignals(False)

        if self.current_jaw_id:
            for row in range(self._jaw_model.rowCount()):
                idx = self._jaw_model.index(row, 0)
                if idx.data(ROLE_JAW_ID) == self.current_jaw_id:
                    self.jaw_list.setCurrentIndex(idx)
                    self.jaw_list.scrollTo(idx)
                    break

        self.jaw_list.doItemsLayout()
        self.jaw_list.viewport().update()
        self.jaw_list.viewport().repaint()
        self._sync_detached_preview(show_errors=False)

    def toggle_details(self):
        if self._details_hidden:
            if not self.current_jaw_id:
                QMessageBox.information(
                    self,
                    self._t('jaw_library.message.show_details', 'Show details'),
                    self._t('jaw_library.message.select_jaw_first', 'Select a jaw first.'),
                )
                return
            jaw = self.jaw_service.get_jaw(self.current_jaw_id)
            self.populate_details(jaw)
            self.show_details()
            return
        self.hide_details()

    def show_details(self):
        if self._selector_active:
            self._selector_slot_controller.set_selector_panel_mode('details')
            return
        self._details_hidden = False
        self.detail_container.show()
        self.detail_header_container.show()
        if not self._last_splitter_sizes:
            total = max(600, self.splitter.width())
            self._last_splitter_sizes = [int(total * 0.62), int(total * 0.38)]
        self.splitter.setSizes(self._last_splitter_sizes)
        self.refresh_list()

    def hide_details(self):
        if self._selector_active:
            self._selector_slot_controller.set_selector_panel_mode('selector')
            return
        self._details_hidden = True
        if self.detail_container.isVisible():
            self._last_splitter_sizes = self.splitter.sizes()
        self.detail_container.hide()
        self.detail_header_container.hide()
        self.splitter.setSizes([1, 0])
        self.refresh_list()

    def on_current_item_changed(self, current: QModelIndex, previous: QModelIndex):
        if not current.isValid():
            self.current_jaw_id = None
            self._update_selection_count_label()
            self.populate_details(None)
            self._sync_detached_preview(show_errors=False)
            return

        self.current_jaw_id = current.data(ROLE_JAW_ID)
        self._update_selection_count_label()

        if not self._details_hidden:
            jaw = self.jaw_service.get_jaw(self.current_jaw_id)
            self.populate_details(jaw)
        self._sync_detached_preview(show_errors=False)

    def on_item_double_clicked(self, index: QModelIndex):
        self.current_jaw_id = index.data(ROLE_JAW_ID)
        if QApplication.keyboardModifiers() & Qt.ControlModifier:
            self.edit_jaw()
            return
        if self._details_hidden:
            self.populate_details(self.jaw_service.get_jaw(self.current_jaw_id))
            self.show_details()
        else:
            self.hide_details()

    def _save_from_dialog(self, dlg, original_jaw_id: str | None = None):
        try:
            data = dlg.get_jaw_data()
            self.jaw_service.save_jaw(data)
            new_jaw_id = data['jaw_id']
            # If the Jaw ID was renamed during edit, remove the old record.
            if original_jaw_id and original_jaw_id != new_jaw_id:
                self.jaw_service.delete_jaw(original_jaw_id)
            self.current_jaw_id = new_jaw_id
            self.refresh_list()
            self.populate_details(self.jaw_service.get_jaw(self.current_jaw_id))
        except ValueError as exc:
            QMessageBox.warning(self, self._t('tool_library.error.invalid_data', 'Invalid data'), str(exc))

    def add_jaw(self):
        dlg = AddEditJawDialog(self, translate=self._t)
        if dlg.exec() == QDialog.Accepted:
            self._save_from_dialog(dlg)

    def edit_jaw(self):
        selected_ids = self._selected_jaw_ids()
        if not selected_ids:
            QMessageBox.information(
                self,
                self._t('jaw_library.action.edit_jaw', 'Edit jaw'),
                self._t('jaw_library.message.select_jaw_first', 'Select a jaw first.'),
            )
            return
        if len(selected_ids) > 1:
            mode = ask_multi_edit_mode(self, len(selected_ids), self._t)
            if mode == 'batch':
                self._batch_edit_jaws(selected_ids)
            elif mode == 'group':
                self._group_edit_jaws(selected_ids)
            return
        jaw = self.jaw_service.get_jaw(selected_ids[0])
        dlg = AddEditJawDialog(self, jaw=jaw, translate=self._t)
        if dlg.exec() == QDialog.Accepted:
            self._save_from_dialog(dlg, original_jaw_id=jaw.get('jaw_id', ''))

    def delete_jaw(self):
        if not self.current_jaw_id:
            QMessageBox.information(
                self,
                self._t('jaw_library.action.delete_jaw', 'Delete jaw'),
                self._t('jaw_library.message.select_jaw_first', 'Select a jaw first.'),
            )
            return
        box = QMessageBox(self)
        setup_editor_dialog(box)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(self._t('jaw_library.action.delete_jaw', 'Delete jaw'))
        box.setText(self._t('jaw_library.message.delete_jaw_prompt', 'Delete jaw {jaw_id}?', jaw_id=self.current_jaw_id))
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

        yes_btn = box.button(QMessageBox.Yes)
        no_btn = box.button(QMessageBox.No)
        if yes_btn is not None:
            yes_btn.setText(self._t('common.yes', 'Yes'))
            yes_btn.setProperty('panelActionButton', True)
            yes_btn.setProperty('dangerAction', True)
        if no_btn is not None:
            no_btn.setText(self._t('common.no', 'No'))
            no_btn.setProperty('panelActionButton', True)
            no_btn.setProperty('secondaryAction', True)

        if box.exec() != QMessageBox.Yes:
            return
        self.jaw_service.delete_jaw(self.current_jaw_id)
        self.current_jaw_id = None
        self.refresh_list()
        self.populate_details(None)

    def copy_jaw(self):
        if not self.current_jaw_id:
            QMessageBox.information(
                self,
                self._t('jaw_library.action.copy_jaw', 'Copy jaw'),
                self._t('jaw_library.message.select_jaw_first', 'Select a jaw first.'),
            )
            return

        jaw = self.jaw_service.get_jaw(self.current_jaw_id)
        if not jaw:
            return

        new_id, ok = self._prompt_text(
            self._t('jaw_library.action.copy_jaw', 'Copy jaw'),
            self._t('jaw_library.prompt.new_jaw_id', 'New Jaw ID:'),
        )
        if not ok or not new_id.strip():
            return

        copied = dict(jaw)
        copied['jaw_id'] = new_id.strip()
        try:
            self.jaw_service.save_jaw(copied)
            self.current_jaw_id = copied['jaw_id']
            self.refresh_list()
            self.populate_details(self.jaw_service.get_jaw(self.current_jaw_id))
        except ValueError as exc:
            QMessageBox.warning(self, self._t('jaw_library.action.copy_jaw', 'Copy jaw'), str(exc))

    def _prompt_text(self, title: str, label: str, initial: str = '') -> tuple[str, bool]:
        dlg = QDialog(self)
        setup_editor_dialog(dlg)
        dlg.setWindowTitle(title)
        dlg.setModal(True)

        root = QVBoxLayout(dlg)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        prompt = QLabel(label)
        prompt.setProperty('detailFieldKey', True)
        prompt.setWordWrap(True)
        root.addWidget(prompt)

        editor = QLineEdit()
        editor.setText(initial)
        root.addWidget(editor)

        buttons = create_dialog_buttons(
            dlg,
            save_text=self._t('common.ok', 'OK'),
            cancel_text=self._t('common.cancel', 'Cancel'),
            on_save=dlg.accept,
            on_cancel=dlg.reject,
        )
        root.addWidget(buttons)

        apply_secondary_button_theme(dlg, buttons.button(QDialogButtonBox.Save))
        editor.setFocus()
        editor.selectAll()

        accepted = dlg.exec() == QDialog.Accepted
        return editor.text(), accepted

    def apply_localization(self, translate: Callable[[str, str | None], str] | None = None):
        if translate is not None:
            self._translate = translate
        if hasattr(self, 'toolbar_title_label'):
            self.toolbar_title_label.setText(self._t('tool_library.module.jaws', 'JAWS'))
        if hasattr(self, 'search'):
            self.search.setPlaceholderText(
                self._t('jaw_library.search.placeholder', 'Search jaw ID, type, spindle, diameter, work, washer or notes')
            )
        if hasattr(self, 'detail_section_label'):
            self.detail_section_label.setText(self._t('jaw_library.section.details', 'Jaw details'))
        if hasattr(self, 'selector_toggle_btn'):
            if self._selector_active and self._selector_panel_mode == 'selector':
                self.selector_toggle_btn.setText(self._t('tool_library.selector.mode_details', 'DETAILS'))
            else:
                self.selector_toggle_btn.setText(self._t('tool_library.selector.mode_selector', 'SELECTOR'))
        if hasattr(self, 'selector_hint_label'):
            self.selector_hint_label.setText(
                self._t('tool_library.selector.jaw_hint', 'Drag jaws from the catalog to SP1 or SP2.')
            )
        if hasattr(self, 'selector_header_title_label'):
            self.selector_header_title_label.setText(self._t('jaw_library.selector.header_title', 'Jaw Selector'))
        if hasattr(self, 'selector_module_value_label'):
            self.selector_module_value_label.setText(self._t('tool_library.selector.jaws', 'Jaws'))
        if hasattr(self, 'selector_sp1_slot'):
            self.selector_sp1_slot.set_title(self._t('jaw_library.selector.sp1_slot', 'SP1 jaw'))
            self.selector_sp1_slot.set_drop_placeholder_text(self._t('jaw_library.selector.drop_here', 'Drop jaw here'))
        if hasattr(self, 'selector_sp2_slot'):
            self.selector_sp2_slot.set_title(self._t('jaw_library.selector.sp2_slot', 'SP2 jaw'))
            self.selector_sp2_slot.set_drop_placeholder_text(self._t('jaw_library.selector.drop_here', 'Drop jaw here'))
        if hasattr(self, 'selector_remove_btn'):
            self.selector_remove_btn.setToolTip(self._t('tool_library.selector.remove', 'Remove'))
        if hasattr(self, 'selector_done_btn'):
            self.selector_done_btn.setText(self._t('tool_library.selector.done', 'DONE'))
        if hasattr(self, 'selector_cancel_btn'):
            self.selector_cancel_btn.setText(self._t('tool_library.selector.cancel', 'CANCEL'))
        self._update_selector_spindle_ui()
        if hasattr(self, 'edit_btn'):
            self.edit_btn.setText(self._t('jaw_library.action.edit_jaw_button', 'EDIT JAW'))
        if hasattr(self, 'delete_btn'):
            self.delete_btn.setText(self._t('jaw_library.action.delete_jaw_button', 'DELETE JAW'))
        if hasattr(self, 'add_btn'):
            self.add_btn.setText(self._t('jaw_library.action.add_jaw_button', 'ADD JAW'))
        if hasattr(self, 'copy_btn'):
            self.copy_btn.setText(self._t('jaw_library.action.copy_jaw_button', 'COPY JAW'))
        if hasattr(self, 'module_switch_label'):
            self.module_switch_label.setText(self._t('tool_library.module.switch_to', 'Switch to'))
        if hasattr(self, 'module_toggle_btn'):
            target = (self.module_toggle_btn.text() or '').strip().upper()
            self.set_module_switch_target('tools' if target == self._t('tool_library.module.tools', 'TOOLS') else target)
        self._build_type_filter_items()
        for mode, btn in self.view_buttons:
            btn.setText(self._nav_mode_title(mode))
        self._selector_slot_controller.refresh_selector_slots()
        self._update_selection_count_label()
        self.refresh_list()
        if self.current_jaw_id:
            self.populate_details(self.jaw_service.get_jaw(self.current_jaw_id))
        else:
            self.populate_details(None)


