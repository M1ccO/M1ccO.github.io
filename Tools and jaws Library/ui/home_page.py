
import json
import shutil
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt, QSize, QUrl, QTimer, QModelIndex, QMimeData, Signal
from PySide6.QtGui import QDrag, QIcon, QDesktopServices, QFontMetrics, QKeySequence, QShortcut, QStandardItemModel, QStandardItem, QColor, QPainter, QPixmap, QTransform
# import QtSvg so that SVG image support is initialized early
import PySide6.QtSvg  # noqa: F401
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QDialogButtonBox, QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QScrollArea, QSplitter, QVBoxLayout, QWidget, QSizePolicy, QToolButton
)
from config import (
    EXPORT_DEFAULT_PATH,
    ALL_TOOL_TYPES,
    MILLING_TOOL_TYPES,
    TURNING_TOOL_TYPES,
    TOOL_TYPE_TO_ICON,
    TOOL_ICONS_DIR,
    DEFAULT_TOOL_ICON,
)
from ui.tool_editor_dialog import AddEditToolDialog
from ui.tool_catalog_delegate import (
    ToolCatalogDelegate, tool_icon_for_type,
    ROLE_TOOL_ID, ROLE_TOOL_DATA, ROLE_TOOL_ICON, ROLE_TOOL_UID,
)
from ui.widgets.common import add_shadow, apply_shared_dropdown_style
from shared.editor_helpers import (
    apply_secondary_button_theme,
    ask_multi_edit_mode,
    create_titled_section,
    create_dialog_buttons,
    setup_editor_dialog,
    style_panel_action_button,
    style_move_arrow_button,
)
from shared.mini_assignment_card import MiniAssignmentCard

from ui.stl_preview import StlPreviewWidget
from ui.selector_mime import SELECTOR_TOOL_MIME, decode_tool_payload, encode_selector_payload, tool_payload_keys
from ui.selector_state_helpers import (
    default_selector_splitter_sizes,
    normalize_selector_bucket,
    normalize_selector_mode,
    selector_assignments_for_target,
    selector_bucket_map,
)
from ui.selector_ui_helpers import normalize_selector_spindle, selector_spindle_label
from ui.home_page_support import apply_tool_detail_layout_rules
from ui.shared.selector_panel_builders import (
    apply_selector_icon_button,
    build_selector_actions_row,
    build_selector_card_shell,
    build_selector_hint_label,
    build_selector_info_header,
    build_selector_toggle_button,
)


class _ToolCatalogListView(QListView):
    def startDrag(self, supportedActions):
        selection_model = self.selectionModel()
        if selection_model is None:
            return
        indexes = sorted(selection_model.selectedRows(), key=lambda idx: idx.row())
        if not indexes:
            index = self.currentIndex()
            if index.isValid():
                indexes = [index]
        if not indexes:
            return

        payload: list[dict] = []
        for index in indexes:
            tool_id = str(index.data(ROLE_TOOL_ID) or '').strip()
            if not tool_id:
                continue
            entry: dict = {'tool_id': tool_id}
            tool_uid = index.data(ROLE_TOOL_UID)
            try:
                parsed_uid = int(tool_uid) if tool_uid is not None and str(tool_uid).strip() else None
            except Exception:
                parsed_uid = None
            if parsed_uid is not None:
                entry['tool_uid'] = parsed_uid
            tool_data = index.data(ROLE_TOOL_DATA)
            if isinstance(tool_data, dict):
                entry['description'] = str(tool_data.get('description') or '').strip()
                entry['tool_type'] = str(tool_data.get('tool_type') or '').strip()
                entry['default_pot'] = str(tool_data.get('default_pot') or '').strip()
            payload.append(entry)

        if not payload:
            return

        mime = QMimeData()
        encode_selector_payload(mime, SELECTOR_TOOL_MIME, payload)
        drag = QDrag(self)
        drag.setMimeData(mime)

        # Build a semi-transparent ghost card showing the first tool
        first = payload[0]
        ghost_text = first.get('tool_id', '')
        desc = first.get('description', '')
        if desc:
            ghost_text = f'{ghost_text} - {desc}'
        if len(payload) > 1:
            ghost_text += f'  (+{len(payload) - 1})'
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
        from PySide6.QtGui import QFont
        font = QFont()
        font.setPointSizeF(9.0)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.drawText(10, 4, 200, 32, Qt.AlignVCenter | Qt.TextSingleLine, ghost_text)
        painter.end()
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())

        drag.exec(Qt.CopyAction)


class _ToolAssignmentListWidget(QListWidget):
    externalToolsDropped = Signal(list, int)
    orderChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)

    def startDrag(self, supportedActions):
        indexes = sorted(self.selectedIndexes(), key=lambda idx: idx.row())
        if not indexes:
            current = self.currentIndex()
            if current.isValid():
                indexes = [current]
        if not indexes:
            return

        mime = self.model().mimeData(indexes)
        if mime is None:
            mime = QMimeData()

        payload: list[dict] = []
        for index in indexes:
            item = self.item(index.row())
            if item is None:
                continue
            assignment = item.data(Qt.UserRole)
            if isinstance(assignment, dict):
                payload.append(dict(assignment))
        encode_selector_payload(mime, SELECTOR_TOOL_MIME, payload)

        drag = QDrag(self)
        drag.setMimeData(mime)

        first_row = indexes[0].row()
        ghost_item = self.item(first_row)
        ghost_widget = self.itemWidget(ghost_item) if ghost_item is not None else None
        if isinstance(ghost_widget, QWidget):
            card_widget = ghost_widget.findChild(MiniAssignmentCard)
            preview_widget = card_widget if isinstance(card_widget, QWidget) else ghost_widget
            grabbed = preview_widget.grab()
            if not grabbed.isNull():
                translucent = QPixmap(grabbed.size())
                translucent.fill(Qt.transparent)
                painter = QPainter(translucent)
                painter.setOpacity(0.7)
                painter.drawPixmap(0, 0, grabbed)
                painter.end()
                drag.setPixmap(translucent)
                drag.setHotSpot(translucent.rect().center())

        drag.exec(Qt.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_TOOL_MIME):
            event.acceptProposedAction()
            return
        if event.source() is self:
            super().dragEnterEvent(event)
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_TOOL_MIME):
            event.acceptProposedAction()
            return
        if event.source() is self:
            super().dragMoveEvent(event)
            return
        event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasFormat(SELECTOR_TOOL_MIME) and event.source() is not self:
            dropped = decode_tool_payload(event.mimeData())
            point = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            row = self.indexAt(point).row()
            if row < 0:
                row = self.count()
            self.externalToolsDropped.emit(dropped if isinstance(dropped, list) else [], row)
            event.acceptProposedAction()
            return
        super().dropEvent(event)
        if event.source() is self:
            self.orderChanged.emit()

    def mousePressEvent(self, event):
        point = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        if self.itemAt(point) is None:
            self.clearSelection()
            self.setCurrentRow(-1)
        super().mousePressEvent(event)


class _SelectorToolRemoveDropButton(QPushButton):
    toolsDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    @staticmethod
    def _payload_tool_keys(mime: QMimeData) -> list[tuple[str, str | None]]:
        return tool_payload_keys(mime)

    def dragEnterEvent(self, event):
        if self._payload_tool_keys(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if self._payload_tool_keys(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event):
        tool_keys = self._payload_tool_keys(event.mimeData())
        if not tool_keys:
            event.ignore()
            return
        self.toolsDropped.emit(tool_keys)
        event.acceptProposedAction()


class _SelectorAssignmentRowWidget(MiniAssignmentCard):
    def __init__(
        self,
        icon: QIcon,
        text: str,
        subtitle: str = '',
        comment: str = '',
        pot: str = '',
        parent=None,
    ):
        badges: list[str] = []
        if pot:
            badges.append(f'P:{pot}')
        if comment:
            badges.append('C')
        super().__init__(
            icon=icon,
            title=text,
            subtitle=subtitle,
            badges=badges,
            editable=True,
            compact=True,
            parent=parent,
        )
        self.setObjectName('selectorAssignmentRowCard')
        self._apply_visual_style(False)

    def _apply_visual_style(self, selected: bool) -> None:
        background = '#ffffff'
        border = '#00C8FF' if selected else '#99acbf'
        border_width = '2px' if selected else '1px'
        padding = '0px' if selected else '1px'
        title_color = '#24303c' if selected else '#171a1d'
        meta_color = '#2b3136'
        hint_color = '#617180'
        self.setStyleSheet(
            'QFrame#selectorAssignmentRowCard {'
            f'  background-color: {background};'
            f'  border: {border_width} solid {border};'
            '  border-radius: 8px;'
            f'  padding: {padding};'
            '}'
            'QFrame#selectorAssignmentRowCard QLabel {'
            '  background-color: transparent;'
            '  border: none;'
            '}'
            'QFrame#selectorAssignmentRowCard QLabel[miniAssignmentTitle="true"] {'
            f'  color: {title_color};'
            '}'
            'QFrame#selectorAssignmentRowCard QLabel[miniAssignmentMeta="true"] {'
            f'  color: {meta_color};'
            '}'
            'QFrame#selectorAssignmentRowCard QLabel[miniAssignmentHint="true"] {'
            f'  color: {hint_color};'
            '}'
        )

    def set_selected(self, selected: bool):
        super().set_selected(selected)
        self._apply_visual_style(bool(selected))


# ==============================
# Home Page Shell
# ==============================
class HomePage(QWidget):
    def __init__(
        self,
        tool_service,
        export_service,
        settings_service,
        parent=None,
        page_title: str = 'Tool Library',
        view_mode: str = 'home',
        translate=None,
    ):
        super().__init__(parent)
        self.tool_service = tool_service
        self.export_service = export_service
        self.settings_service = settings_service
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self.page_title = page_title
        self.view_mode = (view_mode or 'home').lower()
        self.current_tool_id = None
        self.current_tool_uid = None
        self._details_hidden = True
        self._last_splitter_sizes = None
        self._detached_preview_dialog = None
        self._detached_preview_widget = None
        self._close_preview_shortcut = None
        self._measurement_toggle_btn = None
        self._measurement_filter_combo = None
        self._detached_measurements_enabled = True
        self._detached_measurement_filter = None
        self._detached_preview_last_model_key = None
        self._inline_preview_warmup = None
        self._active_db_name = ''
        self._module_switch_callback = None
        self._external_head_filter = None
        self._head_filter_value = 'HEAD1/2'
        self._master_filter_ids: set[str] = set()
        self._master_filter_active = False
        self._selector_active = False
        self._selector_head = ''
        self._selector_spindle = ''
        self._selector_panel_mode = 'details'
        self._selector_assigned_tools: list[dict] = []
        self._selector_assignments_by_target: dict[str, list[dict]] = {}
        self._selector_saved_details_hidden = True
        self._build_ui()
        self._warmup_preview_engine()
        self.refresh_list()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    @staticmethod
    def _strip_tool_id_prefix(value: str) -> str:
        raw = str(value or '').strip()
        if raw.lower().startswith('t'):
            raw = raw[1:].strip()
        return ''.join(ch for ch in raw if ch.isdigit())

    @classmethod
    def _tool_id_storage_value(cls, value: str) -> str:
        stripped = cls._strip_tool_id_prefix(value)
        return f'T{stripped}' if stripped else ''

    @classmethod
    def _tool_id_display_value(cls, value: str) -> str:
        return cls._tool_id_storage_value(value)

    def _warmup_preview_engine(self):
        """Pre-create a hidden preview widget so first detail-open doesn't flash."""
        if StlPreviewWidget is None:
            return
        self._inline_preview_warmup = StlPreviewWidget(parent=self)
        self._inline_preview_warmup.set_control_hint_text(
            self._t(
                'tool_editor.hint.rotate_pan_zoom',
                'Rotate: left mouse • Pan: right mouse • Zoom: mouse wheel',
            )
        )
        self._inline_preview_warmup.hide()

        def _drop_warmup():
            if self._inline_preview_warmup is not None:
                self._inline_preview_warmup.deleteLater()
                self._inline_preview_warmup = None

        # Keep warmup alive long enough for first user interactions.
        QTimer.singleShot(10000, _drop_warmup)

    def _update_row_type_visibility(self, show: bool):
        """Called when the detail panel opens/closes.
        With the delegate-based list, we just need to trigger a repaint.
        """
        self.tool_list.viewport().update()

    # ==============================
    # Home Page Layout
    # ==============================
    def _build_ui(self):
        root = QVBoxLayout(self)
        # Set all margins to 0 for flush alignment
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        filter_frame = QFrame()
        filter_frame.setObjectName('filterFrame')
        filter_frame.setProperty('card', True)
        self.filter_layout = QHBoxLayout(filter_frame)
        # Left margin must clear the absolutely-positioned rail_title label in
        # main_window, which starts at x=10 on the central widget and can extend
        # ~200px for long Finnish titles, bleeding ~90px into the stack area.
        # 108px ensures the first toolbar button is always visible.
        self.filter_layout.setContentsMargins(108, 6, 0, 6)
        self.filter_layout.setSpacing(4)

        self.toolbar_title_label = QLabel(self.page_title)
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

        # details toggle as icon-only toolbutton (tooltip SVG) - moved next to search
        self.toggle_details_btn = QToolButton()
        self.toggle_details_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / 'tooltip.svg')))
        self.toggle_details_btn.setIconSize(QSize(28, 28))
        self.toggle_details_btn.setAutoRaise(True)
        self.toggle_details_btn.setProperty('topBarIconButton', True)
        self.toggle_details_btn.setProperty('secondaryAction', True)
        self.toggle_details_btn.setFixedSize(36, 36)
        self.toggle_details_btn.clicked.connect(self.toggle_details)

        # actual search entry, hidden initially
        self.search = QLineEdit()
        self.search.setPlaceholderText(self._t('tool_library.search.placeholder', 'Tool ID, description, holder or cutting code'))
        self.search.textChanged.connect(self.refresh_list)
        self.search.setVisible(False)
        # restrict search width so it doesn't force layout centering
        from PySide6.QtWidgets import QSizePolicy
        self.search.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.search.setMaximumWidth(300)

        # type filter icon (initially no active filter)
        self.filter_icon = QToolButton()
        self.filter_icon.setIcon(QIcon(str(TOOL_ICONS_DIR / 'filter_arrow_right.svg')))
        # match search button size
        self.filter_icon.setIconSize(QSize(28, 28))
        self.filter_icon.setAutoRaise(True)
        self.filter_icon.setProperty('topBarIconButton', True)
        self.filter_icon.setFixedSize(36, 36)
        self.filter_icon.clicked.connect(self._clear_filter)

        self.type_filter = QComboBox()
        self.type_filter.setObjectName('topTypeFilter')
        self._build_tool_type_filter_items()
        self.type_filter.setMaxVisibleItems(8)
        type_popup_view = self.type_filter.view()
        type_popup_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        type_popup_view.setMinimumHeight(0)
        type_popup_view.setMaximumHeight(8 * 40)
        type_popup_view.window().setMinimumHeight(0)
        type_popup_view.window().setMaximumHeight(8 * 40 + 8)
        # make the combo just wide enough for its content, don't stretch
        from PySide6.QtWidgets import QSizePolicy
        self.type_filter.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.type_filter.setMinimumWidth(60)  # kept narrow from stylesheet
        self.type_filter.currentIndexChanged.connect(self._on_type_changed)
        add_shadow(self.type_filter)
        # give property hover tracking and monitor the popup view
        self.type_filter.installEventFilter(self)
        self.type_filter.view().installEventFilter(self)
        apply_shared_dropdown_style(self.type_filter)

        self.preview_window_btn = QToolButton()
        self.preview_window_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / '3d_icon.svg')))
        self.preview_window_btn.setIconSize(QSize(28, 28))
        self.preview_window_btn.setAutoRaise(True)
        self.preview_window_btn.setProperty('topBarIconButton', True)
        self.preview_window_btn.setCheckable(True)
        self.preview_window_btn.setToolTip(self._t('tool_library.preview.toggle', 'Toggle detached 3D preview'))
        self.preview_window_btn.setFixedSize(36, 36)
        self.preview_window_btn.clicked.connect(self.toggle_preview_window)

        # right-side details header that stays aligned with top-bar icons
        self.detail_header_container = QWidget()
        detail_top = QHBoxLayout(self.detail_header_container)
        detail_top.setContentsMargins(0, 0, 0, 0)
        detail_top.setSpacing(6)
        self.detail_section_label = QLabel(self._t('tool_library.section.tool_details', 'Tool details'))
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

        self._rebuild_filter_row()
        root.addWidget(filter_frame)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setChildrenCollapsible(False)

        # catalogue and detail panes
        left_card = QFrame()
        left_card.setProperty('catalogShell', True)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        self.tool_list = _ToolCatalogListView()
        self.tool_list.setObjectName('toolCatalog')
        self.tool_list.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.tool_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tool_list.setSelectionMode(QListView.ExtendedSelection)
        self.tool_list.setDragEnabled(True)
        self.tool_list.setMouseTracking(True)   # needed for hover in delegate
        self.tool_list.setStyleSheet(
            "QListView#toolCatalog { border: none; outline: none; padding: 8px; }"
            " QListView#toolCatalog::item { background: transparent; border: none; }"
        )
        self.tool_list.setSpacing(4)
        self._tool_model = QStandardItemModel(self)
        self.tool_list.setModel(self._tool_model)
        self._tool_delegate = ToolCatalogDelegate(
            parent=self.tool_list,
            view_mode=self.view_mode,
            translate=self._t,
        )
        self.tool_list.setItemDelegate(self._tool_delegate)
        self.tool_list.selectionModel().currentChanged.connect(self._on_current_changed)
        self.tool_list.selectionModel().selectionChanged.connect(self._on_multi_selection_changed)
        self.tool_list.doubleClicked.connect(self._on_double_clicked)
        self.tool_list.installEventFilter(self)
        self.tool_list.viewport().installEventFilter(self)
        left_layout.addWidget(self.tool_list, 1)
        self.splitter.addWidget(left_card)

        self.detail_container = QWidget()
        self.detail_container.setContentsMargins(0, 0, 0, 0)
        self.detail_container.setMinimumWidth(220)
        self.detail_container.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        dc_layout = QVBoxLayout(self.detail_container)
        dc_layout.setContentsMargins(0, 0, 0, 0)
        dc_layout.setSpacing(2)

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
        self.detail_panel.setMinimumWidth(0)
        self.detail_panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.detail_layout = QVBoxLayout(self.detail_panel)
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_layout.setSpacing(10)
        self.detail_scroll.setWidget(self.detail_panel)
        self.detail_layout.addWidget(self._build_placeholder_details())
        detail_card_layout.addWidget(self.detail_scroll, 1)
        dc_layout.addWidget(self.detail_card, 1)

        self._build_selector_card(dc_layout)

        self.splitter.addWidget(self.detail_container)
        root.addWidget(self.splitter, 1)

        self.detail_container.hide()
        self.detail_header_container.hide()
        self.splitter.setSizes([1, 0])

        self._build_bottom_bars(root)


    def _build_selector_card(self, dc_layout: QVBoxLayout) -> None:
        """Build the selector context card shown when assigning tools externally."""
        self.selector_card, self.selector_scroll, self.selector_panel, selector_layout = build_selector_card_shell(spacing=8)
        selector_card_layout = QVBoxLayout(self.selector_card)
        selector_card_layout.setContentsMargins(0, 0, 0, 0)
        selector_card_layout.setSpacing(0)

        # ── Selector target header (mirrors detail panel header treatment) ──
        (
            self.selector_info_header,
            self.selector_header_title_label,
            self.selector_spindle_value_label,
            self.selector_head_value_label,
        ) = build_selector_info_header(
            title_text=self._t('tool_library.selector.header_title', 'Tool Selector'),
            left_badge_text='SP1',
            right_badge_text='HEAD1',
        )
        selector_layout.addWidget(self.selector_info_header, 0)

        # ── DETAILS + SP toggle row (same level, symmetric widths) ──
        ctx_row = QHBoxLayout()
        ctx_row.setContentsMargins(0, 0, 0, 0)
        ctx_row.setSpacing(10)
        ctx_row.addStretch(1)

        self.selector_toggle_btn = build_selector_toggle_button(
            text=self._t('tool_library.selector.mode_details', 'DETAILS'),
            on_clicked=self._on_selector_toggle_clicked,
        )
        ctx_row.addWidget(self.selector_toggle_btn, 0)

        self.selector_spindle_btn = QPushButton('SP1')
        self.selector_spindle_btn.setProperty('panelActionButton', True)
        self.selector_spindle_btn.setCheckable(True)
        self.selector_spindle_btn.setMinimumWidth(120)
        self.selector_spindle_btn.setMaximumWidth(140)
        self.selector_spindle_btn.setFixedHeight(30)
        self.selector_spindle_btn.setProperty('spindle', 'main')
        self.selector_spindle_btn.clicked.connect(self._toggle_selector_spindle)
        style_panel_action_button(self.selector_spindle_btn)
        ctx_row.addWidget(self.selector_spindle_btn, 0)
        ctx_row.addStretch(1)
        selector_layout.addLayout(ctx_row)

        self.selector_drop_hint = build_selector_hint_label(
            text=self._t(
                'tool_library.selector.drop_hint',
                'Drag tools from the catalog to this list and reorder them by dragging.',
            ),
            multiline=True,
        )
        selector_layout.addWidget(self.selector_drop_hint, 0)

        self.selector_assignment_list = _ToolAssignmentListWidget()
        self.selector_assignment_list.setObjectName('toolIdsOrderList')
        self.selector_assignment_list.setStyleSheet(
            '#toolIdsOrderList { background: transparent; border: none; }'
            '#toolIdsOrderList::viewport { background: transparent; border: none; }'
            '#toolIdsOrderList::item { background: transparent; border: none; }'
        )
        self.selector_assignment_list.externalToolsDropped.connect(self._on_selector_tools_dropped)
        self.selector_assignment_list.orderChanged.connect(self._sync_selector_assignment_order)
        self.selector_assignment_list.itemSelectionChanged.connect(self._update_selector_assignment_buttons)
        self.selector_assignment_list.itemSelectionChanged.connect(self._sync_selector_card_selection_states)

        self.selector_assignments_frame = create_titled_section(self._selector_assignments_section_title())
        self.selector_assignments_frame.setProperty('selectorAssignmentsFrame', True)
        self.selector_assignments_frame.setProperty('toolIdsPanel', True)
        self.selector_assignments_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        selector_assignments_layout = QVBoxLayout(self.selector_assignments_frame)
        selector_assignments_layout.setContentsMargins(8, 10, 8, 8)
        selector_assignments_layout.setSpacing(0)
        selector_assignments_layout.addWidget(self.selector_assignment_list, 1)
        selector_layout.addWidget(self.selector_assignments_frame, 1)

        # Icon button row (matches Work Editor tool-IDs pattern).
        selector_actions = build_selector_actions_row(spacing=4)

        self.selector_move_up_btn = QPushButton('\u25B2')
        style_move_arrow_button(self.selector_move_up_btn, '\u25B2',
                                self._t('tool_library.selector.move_up', 'Move Up'))
        self.selector_move_up_btn.clicked.connect(self._move_selector_up)
        selector_actions.addWidget(self.selector_move_up_btn)

        self.selector_move_down_btn = QPushButton('\u25BC')
        style_move_arrow_button(self.selector_move_down_btn, '\u25BC',
                                self._t('tool_library.selector.move_down', 'Move Down'))
        self.selector_move_down_btn.clicked.connect(self._move_selector_down)
        selector_actions.addWidget(self.selector_move_down_btn)

        self.selector_remove_btn = _SelectorToolRemoveDropButton()
        apply_selector_icon_button(
            self.selector_remove_btn,
            icon_path=TOOL_ICONS_DIR / 'delete.svg',
            tooltip=self._t('tool_library.selector.remove', 'Remove'),
            danger=True,
        )
        self.selector_remove_btn.clicked.connect(self._remove_selector_assignment)
        self.selector_remove_btn.toolsDropped.connect(self._remove_selector_assignments_by_keys)
        selector_actions.addWidget(self.selector_remove_btn)

        self.selector_comment_btn = QPushButton()
        apply_selector_icon_button(
            self.selector_comment_btn,
            icon_path=TOOL_ICONS_DIR / 'comment.svg',
            tooltip=self._t('tool_library.selector.add_comment', 'Add Comment'),
        )
        self.selector_comment_btn.clicked.connect(self._add_selector_comment)
        selector_actions.addWidget(self.selector_comment_btn)

        self.selector_delete_comment_btn = QPushButton()
        apply_selector_icon_button(
            self.selector_delete_comment_btn,
            icon_path=TOOL_ICONS_DIR / 'comment_disable.svg',
            tooltip=self._t('tool_library.selector.delete_comment', 'Delete Comment'),
        )
        self.selector_delete_comment_btn.clicked.connect(self._delete_selector_comment)
        selector_actions.addWidget(self.selector_delete_comment_btn)

        selector_actions.addStretch(1)
        selector_layout.addLayout(selector_actions)
        self.selector_scroll.setWidget(self.selector_panel)
        selector_card_layout.addWidget(self.selector_scroll, 1)
        dc_layout.addWidget(self.selector_card, 1)

    def _build_bottom_bars(self, root: QVBoxLayout) -> None:
        """Build normal and selector-mode bottom action bars."""
        self.button_bar = QFrame()
        self.button_bar.setProperty('bottomBar', True)
        button_layout = QHBoxLayout(self.button_bar)
        button_layout.setContentsMargins(10, 8, 10, 8)
        button_layout.setSpacing(8)

        self.copy_btn = QPushButton(self._t('tool_library.action.copy_tool', 'COPY TOOL'))
        self.copy_btn.setProperty('panelActionButton', True)
        self.copy_btn.clicked.connect(self.copy_tool)
        self.edit_btn = QPushButton(self._t('tool_library.action.edit_tool', 'EDIT TOOL'))
        self.edit_btn.setProperty('panelActionButton', True)
        self.edit_btn.clicked.connect(self.edit_tool)
        self.delete_btn = QPushButton(self._t('tool_library.action.delete_tool', 'DELETE TOOL'))
        self.delete_btn.setProperty('panelActionButton', True)
        self.delete_btn.setProperty('dangerAction', True)
        self.delete_btn.clicked.connect(self.delete_tool)
        self.add_btn = QPushButton(self._t('tool_library.action.add_tool', 'ADD TOOL'))
        self.add_btn.setProperty('panelActionButton', True)
        self.add_btn.setProperty('primaryAction', True)
        self.add_btn.clicked.connect(self.add_tool)

        self.module_switch_label = QLabel(self._t('tool_library.module.switch_to', 'Switch to'))
        self.module_switch_label.setProperty('pageSubtitle', True)
        self.module_toggle_btn = QPushButton(self._t('tool_library.module.jaws', 'JAWS'))
        self.module_toggle_btn.setProperty('panelActionButton', True)
        self.module_toggle_btn.setFixedHeight(28)
        self.module_toggle_btn.clicked.connect(self._on_module_switch_clicked)

        button_layout.addWidget(self.module_switch_label, 0, Qt.AlignLeft | Qt.AlignVCenter)
        button_layout.addWidget(self.module_toggle_btn, 0, Qt.AlignLeft | Qt.AlignVCenter)
        button_layout.addStretch(1)
        self.selection_count_label = QLabel('')
        self.selection_count_label.setProperty('detailHint', True)
        self.selection_count_label.setStyleSheet('background: transparent; border: none;')
        self.selection_count_label.hide()
        button_layout.addWidget(self.selection_count_label, 0, Qt.AlignBottom)
        button_layout.addWidget(self.add_btn)
        button_layout.addWidget(self.edit_btn)
        button_layout.addWidget(self.delete_btn)
        button_layout.addWidget(self.copy_btn)
        root.addWidget(self.button_bar)

        # ── Selector bottom bar (VALMIS / PERUUTA) — shown in selector mode ──
        self.selector_bottom_bar = QFrame()
        self.selector_bottom_bar.setProperty('bottomBar', True)
        self.selector_bottom_bar.setVisible(False)
        sel_bar_layout = QHBoxLayout(self.selector_bottom_bar)
        sel_bar_layout.setContentsMargins(10, 8, 10, 8)
        sel_bar_layout.setSpacing(8)
        sel_bar_layout.addStretch(1)

        self.selector_cancel_btn = QPushButton(self._t('tool_library.selector.cancel', 'CANCEL'))
        self.selector_cancel_btn.setProperty('panelActionButton', True)
        self.selector_cancel_btn.clicked.connect(self._on_selector_cancel)
        sel_bar_layout.addWidget(self.selector_cancel_btn)

        self.selector_done_btn = QPushButton(self._t('tool_library.selector.done', 'DONE'))
        self.selector_done_btn.setProperty('panelActionButton', True)
        self.selector_done_btn.setProperty('primaryAction', True)
        self.selector_done_btn.clicked.connect(self._on_selector_done)
        sel_bar_layout.addWidget(self.selector_done_btn)
        root.addWidget(self.selector_bottom_bar)

        self._update_selector_assignment_buttons()

    def _on_module_switch_clicked(self):
        if callable(self._module_switch_callback):
            self._module_switch_callback()

    def set_module_switch_handler(self, callback):
        self._module_switch_callback = callback

    def set_page_title(self, title: str):
        self.page_title = str(title or '')
        if hasattr(self, 'toolbar_title_label'):
            self.toolbar_title_label.setText(self.page_title)

    def set_module_switch_target(self, target: str):
        target_text = (target or '').strip().upper() or 'JAWS'
        display = self._t('tool_library.module.tools', 'TOOLS') if target_text == 'TOOLS' else self._t('tool_library.module.jaws', 'JAWS')
        self.module_toggle_btn.setText(display)
        self.module_toggle_btn.setToolTip(self._t('tool_library.module.switch_to_target', 'Switch to {target} module', target=display))

    def set_master_filter(self, tool_ids, active: bool):
        self._master_filter_ids = {str(t).strip() for t in (tool_ids or []) if str(t).strip()}
        self._master_filter_active = bool(active) and bool(self._master_filter_ids)
        self.refresh_list()

    @staticmethod
    def _selector_tool_key(tool: dict | None) -> str:
        if not isinstance(tool, dict):
            return ''
        tool_uid = tool.get('tool_uid', tool.get('uid'))
        if tool_uid is not None and str(tool_uid).strip():
            return f'uid:{tool_uid}'
        tool_id = str(tool.get('tool_id') or tool.get('id') or '').strip()
        return f'id:{tool_id}' if tool_id else ''

    @staticmethod
    def _normalize_selector_tool(tool: dict | None) -> dict | None:
        if not isinstance(tool, dict):
            return None
        tool_id = str(tool.get('tool_id') or tool.get('id') or '').strip()
        if not tool_id:
            return None
        normalized = {'tool_id': tool_id}
        tool_uid = tool.get('tool_uid', tool.get('uid'))
        try:
            parsed_uid = int(tool_uid) if tool_uid is not None and str(tool_uid).strip() else None
        except Exception:
            parsed_uid = None
        if parsed_uid is not None:
            normalized['tool_uid'] = parsed_uid
        for key in ('description', 'tool_type', 'default_pot'):
            value = str(tool.get(key) or '').strip()
            if value:
                normalized[key] = value
        comment = str(tool.get('comment') or '').strip()
        if comment:
            normalized['comment'] = comment
        return normalized

    @staticmethod
    def _selector_spindle_label(spindle: str) -> str:
        return selector_spindle_label(spindle)

    @staticmethod
    def _normalize_selector_head_value(head: str) -> str:
        return 'HEAD2' if str(head or '').strip().upper() == 'HEAD2' else 'HEAD1'

    @staticmethod
    def _normalize_selector_spindle_value(spindle: str) -> str:
        return normalize_selector_spindle(spindle)

    @classmethod
    def _selector_target_key(cls, head: str, spindle: str) -> str:
        return f"{cls._normalize_selector_head_value(head)}:{cls._normalize_selector_spindle_value(spindle)}"

    def _selector_current_target_key(self) -> str:
        return self._selector_target_key(self._selector_head or 'HEAD1', self._current_selector_spindle_value())

    def _store_selector_bucket_for_current_target(self) -> None:
        key = self._selector_current_target_key()
        self._selector_assignments_by_target[key] = [dict(item) for item in self._selector_assigned_tools]

    def _load_selector_bucket_for_current_target(self) -> None:
        self._selector_assigned_tools = selector_assignments_for_target(
            self._selector_assignments_by_target,
            self._selector_current_target_key(),
        )

    def _current_selector_spindle_value(self) -> str:
        if hasattr(self, 'selector_spindle_btn'):
            return 'sub' if self.selector_spindle_btn.property('spindle') == 'sub' else 'main'
        return 'sub' if str(self._selector_spindle or '').strip().lower() == 'sub' else 'main'

    def _update_selector_spindle_button_text(self):
        if not hasattr(self, 'selector_spindle_btn'):
            return
        spindle = self._current_selector_spindle_value()
        self.selector_spindle_btn.setText(self._selector_spindle_label(spindle))
        self.selector_spindle_btn.setChecked(spindle == 'sub')
        if hasattr(self, 'selector_spindle_value_label'):
            self.selector_spindle_value_label.setText(self._selector_spindle_label(spindle))

    def _update_selector_context_header(self) -> None:
        head = self._normalize_selector_head_value(self._selector_head or 'HEAD1')
        spindle = self._current_selector_spindle_value()
        if hasattr(self, 'selector_head_value_label'):
            self.selector_head_value_label.setText(head)
        if hasattr(self, 'selector_spindle_value_label'):
            self.selector_spindle_value_label.setText(self._selector_spindle_label(spindle))

    def _set_selector_spindle_value(self, spindle: str):
        normalized = normalize_selector_spindle(spindle)
        self._selector_spindle = normalized
        if hasattr(self, 'selector_spindle_btn'):
            self.selector_spindle_btn.setProperty('spindle', normalized)
            self._update_selector_spindle_button_text()

    def _selector_assignments_section_title(self) -> str:
        if self._normalize_selector_head_value(self._selector_head or 'HEAD1') == 'HEAD2':
            return self._t('tool_library.selector.head2_tools', 'Head 2 Tools')
        return self._t('tool_library.selector.head1_tools', 'Head 1 Tools')

    def _update_selector_assignments_section_title(self) -> None:
        if hasattr(self, 'selector_assignments_frame') and hasattr(self.selector_assignments_frame, 'setTitle'):
            self.selector_assignments_frame.setTitle(self._selector_assignments_section_title())

    def _selector_selected_rows(self) -> list[int]:
        if not hasattr(self, 'selector_assignment_list'):
            return []
        rows = sorted({index.row() for index in self.selector_assignment_list.selectedIndexes()})
        return [row for row in rows if 0 <= row < len(self._selector_assigned_tools)]

    def _update_selector_assignment_buttons(self):
        if not hasattr(self, 'selector_remove_btn'):
            return
        selected_rows = self._selector_selected_rows()
        has_row = bool(selected_rows)
        single_selected = len(selected_rows) == 1
        current_row = selected_rows[0] if single_selected else -1
        has_items = bool(getattr(self, 'selector_assignment_list', None) and self.selector_assignment_list.count() > 0)
        self.selector_remove_btn.setEnabled(has_row or has_items)
        self.selector_move_up_btn.setEnabled(single_selected and current_row > 0)
        self.selector_move_down_btn.setEnabled(single_selected and current_row < self.selector_assignment_list.count() - 1)
        self.selector_comment_btn.setEnabled(single_selected)
        self.selector_delete_comment_btn.setEnabled(single_selected)

    def _refresh_selector_assignment_rows(self):
        if not hasattr(self, 'selector_assignment_list'):
            return
        self._rebuild_selector_assignment_list()

    def _sync_selector_card_selection_states(self):
        if not hasattr(self, 'selector_assignment_list'):
            return
        for row in range(self.selector_assignment_list.count()):
            item = self.selector_assignment_list.item(row)
            widget = self.selector_assignment_list.itemWidget(item)
            if isinstance(widget, MiniAssignmentCard):
                widget.set_selected(item.isSelected())
                continue
            card = widget.findChild(MiniAssignmentCard) if isinstance(widget, QWidget) else None
            if isinstance(card, MiniAssignmentCard):
                card.set_selected(item.isSelected())

    def _sync_selector_assignment_order(self):
        if not hasattr(self, 'selector_assignment_list'):
            return
        ordered: list[dict] = []
        for row in range(self.selector_assignment_list.count()):
            item = self.selector_assignment_list.item(row)
            assignment = item.data(Qt.UserRole)
            normalized = self._normalize_selector_tool(assignment)
            if normalized is not None:
                ordered.append(normalized)
        self._selector_assigned_tools = ordered
        self._refresh_selector_assignment_rows()
        self._update_selector_assignment_buttons()

    def _rebuild_selector_assignment_list(self):
        if not hasattr(self, 'selector_assignment_list'):
            return
        current = self.selector_assignment_list.currentRow()
        selected_rows = self._selector_selected_rows()
        self.selector_assignment_list.blockSignals(True)
        self.selector_assignment_list.clear()
        for row, assignment in enumerate(self._selector_assigned_tools):
            tool_id = str(assignment.get('tool_id') or '').strip()
            description = str(assignment.get('description') or '').strip()
            comment = str(assignment.get('comment') or '').strip()
            pot = str(assignment.get('default_pot') or '').strip()
            title = f'{row + 1}. {tool_id}'
            if description:
                title = f'{title}  -  {description}'
            subtitle = comment
            badges: list[str] = []
            if pot:
                badges.append(f'P:{pot}')
            if comment:
                badges.append('C')
            icon = tool_icon_for_type(str(assignment.get('tool_type') or '').strip())
            item = QListWidgetItem()
            item.setData(Qt.UserRole, dict(assignment))
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
            item.setSizeHint(QSize(0, 50 if comment else 42))
            self.selector_assignment_list.addItem(item)
            card = _SelectorAssignmentRowWidget(
                icon=icon,
                text=title,
                subtitle=subtitle,
                comment=assignment.get('comment', ''),
                pot=pot,
                parent=self.selector_assignment_list,
            )
            card.setProperty('hasComment', bool(comment))
            card.editRequested.connect(lambda r=row: self._inline_edit_selector_row(r))
            row_host = QWidget(self.selector_assignment_list)
            row_host.setProperty('editorTransparentPanel', True)
            row_host.setAttribute(Qt.WA_StyledBackground, False)
            row_host.setStyleSheet('background: transparent; border: none;')
            row_layout = QVBoxLayout(row_host)
            row_layout.setContentsMargins(0, 0, 0, 7)
            row_layout.setSpacing(0)
            row_layout.addWidget(card)
            self.selector_assignment_list.setItemWidget(item, row_host)
        self.selector_assignment_list.blockSignals(False)
        for row in selected_rows:
            if 0 <= row < self.selector_assignment_list.count():
                item = self.selector_assignment_list.item(row)
                if item is not None:
                    item.setSelected(True)
        if current >= 0 and current < self.selector_assignment_list.count():
            self.selector_assignment_list.setCurrentRow(current)
        self._sync_selector_card_selection_states()
        self._update_selector_assignment_buttons()

    def _on_selector_tools_dropped(self, dropped_items: list, insert_row: int):
        if not isinstance(dropped_items, list):
            return

        existing_keys = {
            self._selector_tool_key(item)
            for item in self._selector_assigned_tools
            if self._selector_tool_key(item)
        }
        insert_at = insert_row if isinstance(insert_row, int) and insert_row >= 0 else len(self._selector_assigned_tools)
        insert_at = min(insert_at, len(self._selector_assigned_tools))
        added = False
        for tool in dropped_items:
            normalized = self._normalize_selector_tool(tool)
            if normalized is None:
                continue
            key = self._selector_tool_key(normalized)
            if not key or key in existing_keys:
                continue
            self._selector_assigned_tools.insert(insert_at, normalized)
            existing_keys.add(key)
            insert_at += 1
            added = True

        if added:
            self._rebuild_selector_assignment_list()
            self.selector_assignment_list.setCurrentRow(min(insert_at - 1, self.selector_assignment_list.count() - 1))

    def _remove_selector_assignment(self):
        rows = self._selector_selected_rows()
        if not rows:
            return
        for row in reversed(rows):
            if 0 <= row < len(self._selector_assigned_tools):
                self._selector_assigned_tools.pop(row)
        self._rebuild_selector_assignment_list()
        if self.selector_assignment_list.count() > 0:
            self.selector_assignment_list.setCurrentRow(min(rows[0], self.selector_assignment_list.count() - 1))

    def _remove_selector_assignments_by_keys(self, tool_keys: list[tuple[str, str | None]]):
        if not tool_keys:
            return
        target_counts: dict[tuple[str, str | None], int] = {}
        for key in tool_keys:
            target_counts[key] = target_counts.get(key, 0) + 1
        remaining: list[dict] = []
        for assignment in self._selector_assigned_tools:
            tool_id = str(assignment.get('tool_id') or '').strip()
            tool_uid_raw = assignment.get('tool_uid')
            tool_uid = str(tool_uid_raw).strip() if tool_uid_raw is not None and str(tool_uid_raw).strip() else None
            key = (tool_id, tool_uid)
            if tool_id and target_counts.get(key, 0) > 0:
                target_counts[key] -= 1
                continue
            remaining.append(assignment)
        if len(remaining) != len(self._selector_assigned_tools):
            self._selector_assigned_tools = remaining
            self._rebuild_selector_assignment_list()

    def _move_selector_up(self):
        selected_rows = self._selector_selected_rows()
        if len(selected_rows) != 1:
            return
        row = selected_rows[0]
        if row <= 0 or row >= len(self._selector_assigned_tools):
            return
        self._selector_assigned_tools[row - 1], self._selector_assigned_tools[row] = (
            self._selector_assigned_tools[row], self._selector_assigned_tools[row - 1])
        self._rebuild_selector_assignment_list()
        self.selector_assignment_list.setCurrentRow(row - 1)

    def _move_selector_down(self):
        selected_rows = self._selector_selected_rows()
        if len(selected_rows) != 1:
            return
        row = selected_rows[0]
        if row < 0 or row >= len(self._selector_assigned_tools) - 1:
            return
        self._selector_assigned_tools[row], self._selector_assigned_tools[row + 1] = (
            self._selector_assigned_tools[row + 1], self._selector_assigned_tools[row])
        self._rebuild_selector_assignment_list()
        self.selector_assignment_list.setCurrentRow(row + 1)

    def _add_selector_comment(self):
        selected_rows = self._selector_selected_rows()
        if len(selected_rows) != 1:
            return
        row = selected_rows[0]
        if row < 0 or row >= len(self._selector_assigned_tools):
            return
        current = str(self._selector_assigned_tools[row].get('comment') or '').strip()
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(
            self, self._t('tool_library.selector.add_comment', 'Add Comment'),
            self._t('tool_library.selector.comment_prompt', 'Comment:'),
            text=current,
        )
        if ok:
            self._selector_assigned_tools[row]['comment'] = text.strip()
            self._rebuild_selector_assignment_list()
            self.selector_assignment_list.setCurrentRow(row)

    def _delete_selector_comment(self):
        selected_rows = self._selector_selected_rows()
        if len(selected_rows) != 1:
            return
        row = selected_rows[0]
        if row < 0 or row >= len(self._selector_assigned_tools):
            return
        self._selector_assigned_tools[row].pop('comment', None)
        self._rebuild_selector_assignment_list()
        self.selector_assignment_list.setCurrentRow(row)

    def _inline_edit_selector_row(self, row: int):
        if row < 0 or row >= len(self._selector_assigned_tools):
            return
        assignment = self._selector_assigned_tools[row]
        tool_id = str(assignment.get('tool_id') or '').strip()
        description = str(assignment.get('description') or '').strip()
        pot = str(assignment.get('default_pot') or '').strip()
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(
            self,
            self._t('tool_library.selector.edit_assignment', 'Edit Assignment'),
            f'T-code / Description / Pot  (current: {tool_id})',
            text=f'{tool_id}  |  {description}  |  {pot}',
        )
        if not ok:
            return
        parts = [p.strip() for p in text.split('|')]
        if parts:
            assignment['tool_id'] = parts[0] or tool_id
        if len(parts) > 1:
            assignment['description'] = parts[1]
        if len(parts) > 2:
            assignment['default_pot'] = parts[2]
        self._rebuild_selector_assignment_list()
        self.selector_assignment_list.setCurrentRow(row)

    def _toggle_selector_spindle(self):
        if not self._selector_active or not hasattr(self, 'selector_spindle_btn'):
            return
        self._store_selector_bucket_for_current_target()
        target = 'sub' if self.selector_spindle_btn.isChecked() else 'main'
        self._set_selector_spindle_value(target)
        self._load_selector_bucket_for_current_target()
        self._update_selector_context_header()
        self._update_selector_assignments_section_title()
        self._rebuild_selector_assignment_list()

    def _on_selector_cancel(self):
        """Cancel selector — notify main window to clear the session."""
        main_win = self.window()
        if hasattr(main_win, '_clear_selector_session'):
            main_win._clear_selector_session()
        if hasattr(main_win, '_back_to_setup_manager'):
            main_win._back_to_setup_manager()

    def _on_selector_done(self):
        """Send selection — delegate to main window."""
        main_win = self.window()
        if hasattr(main_win, '_send_selector_selection'):
            main_win._send_selector_selection()

    def _on_selector_toggle_clicked(self):
        if not self._selector_active:
            return
        if self.selector_toggle_btn.isChecked():
            self._set_selector_panel_mode('selector')
        else:
            self._set_selector_panel_mode('details')

    def _set_selector_panel_mode(self, mode: str):
        if not self._selector_active:
            self._selector_panel_mode = 'details'
            if hasattr(self, 'selector_toggle_btn'):
                self.selector_toggle_btn.setChecked(False)
            if hasattr(self, 'selector_card'):
                self.selector_card.setVisible(False)
            if hasattr(self, 'detail_card'):
                self.detail_card.setVisible(True)
            return

        target_mode = normalize_selector_mode(mode)
        self._selector_panel_mode = target_mode
        self._details_hidden = False
        self.detail_container.show()
        self.detail_header_container.show()
        if not self._last_splitter_sizes:
            self._last_splitter_sizes = default_selector_splitter_sizes(self.splitter.width())
        self.splitter.setSizes(self._last_splitter_sizes)

        if target_mode == 'details':
            self.detail_card.setVisible(True)
            self.selector_card.setVisible(False)
            self.detail_section_label.setText(self._t('tool_library.section.tool_details', 'Tool details'))
            self.toggle_details_btn.setText(self._t('tool_library.details.hide', 'HIDE DETAILS'))
            self._update_row_type_visibility(False)
            self.selector_toggle_btn.setChecked(False)
            self.selector_toggle_btn.setText(self._t('tool_library.selector.mode_selector', 'SELECTOR'))
        else:
            self.detail_card.setVisible(False)
            self.selector_card.setVisible(True)
            self.detail_section_label.setText(self._t('tool_library.selector.selection_title', 'Selection'))
            self.toggle_details_btn.setText(self._t('tool_library.details.show', 'SHOW DETAILS'))
            self._update_row_type_visibility(True)
            self.selector_toggle_btn.setChecked(True)
            self.selector_toggle_btn.setText(self._t('tool_library.selector.mode_details', 'DETAILS'))
            # Keep selector rows resilient after UI mode/header refactors.
            self._load_selector_bucket_for_current_target()
            self._rebuild_selector_assignment_list()

    def set_selector_context(
        self,
        active: bool,
        head: str = '',
        spindle: str = '',
        initial_assignments: list[dict] | None = None,
        initial_assignment_buckets: dict[str, list[dict]] | None = None,
    ) -> None:
        was_active = self._selector_active
        self._selector_active = bool(active)
        self._selector_head = self._normalize_selector_head_value(str(head or '').strip().upper())
        self._set_selector_spindle_value(str(spindle or '').strip().lower())
        self.selector_toggle_btn.setVisible(self._selector_active)
        self.toggle_details_btn.setEnabled(not self._selector_active)

        # Toggle bottom bars
        self.button_bar.setVisible(not self._selector_active)
        self.selector_bottom_bar.setVisible(self._selector_active)

        if self._selector_active:
            if not was_active:
                self._selector_saved_details_hidden = self._details_hidden
            loaded_buckets = selector_bucket_map(
                initial_assignment_buckets,
                self._normalize_selector_tool,
                self._selector_tool_key,
                self._selector_target_key,
            )
            if not loaded_buckets and isinstance(initial_assignments, list):
                loaded_buckets[self._selector_current_target_key()] = normalize_selector_bucket(
                    initial_assignments,
                    self._normalize_selector_tool,
                    self._selector_tool_key,
                )

            self._selector_assignments_by_target = loaded_buckets
            self._load_selector_bucket_for_current_target()
            self._update_selector_spindle_button_text()
            self._update_selector_context_header()
            self._update_selector_assignments_section_title()
            self._rebuild_selector_assignment_list()
            self._set_selector_panel_mode('selector')
            return

        self._details_hidden = self._selector_saved_details_hidden
        self._selector_assigned_tools = []
        self._selector_assignments_by_target = {}
        if hasattr(self, 'selector_assignment_list'):
            self.selector_assignment_list.clear()
        self._update_selector_context_header()
        self._set_selector_panel_mode('details')
        self.detail_section_label.setText(self._t('tool_library.section.tool_details', 'Tool details'))
        if self._details_hidden:
            self.detail_container.hide()
            self.detail_header_container.hide()
            self.splitter.setSizes([1, 0])
            self._update_row_type_visibility(True)
        else:
            self.detail_container.show()
            self.detail_header_container.show()
            if not self._last_splitter_sizes:
                self._last_splitter_sizes = default_selector_splitter_sizes(self.splitter.width())
            self.splitter.setSizes(self._last_splitter_sizes)
            self._update_row_type_visibility(False)

    def selector_assigned_tools_for_setup_assignment(self) -> list[dict]:
        self._sync_selector_assignment_order()
        return [dict(item) for item in self._selector_assigned_tools]

    def update_selector_head(self, head: str) -> None:
        """Update the selector HEAD target (called when the HEAD dropdown changes)."""
        if not self._selector_active:
            return
        self._store_selector_bucket_for_current_target()
        self._selector_head = self._normalize_selector_head_value(head)
        self._load_selector_bucket_for_current_target()
        self._update_selector_context_header()
        self._update_selector_assignments_section_title()
        self._rebuild_selector_assignment_list()

    def selector_current_target_for_setup_assignment(self) -> dict:
        return {
            'head': self._normalize_selector_head_value(self._selector_head or 'HEAD1'),
            'spindle': self._normalize_selector_spindle_value(self._current_selector_spindle_value()),
        }

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
        self.filter_layout.addWidget(self.type_filter)
        self.filter_layout.addWidget(self.preview_window_btn)
        self.filter_layout.addStretch(1)
        self.filter_layout.addWidget(self.detail_header_container)

    def set_active_database_name(self, db_name: str):
        self._active_db_name = (db_name or '').strip()

    # ==============================
    # Home Page Filters + List State
    # ==============================
    def _toggle_search(self):
        """Show or hide the search field and update widget order."""
        show = self.search_toggle.isChecked()
        # hide the combo entirely while we rearrange; this prevents it from briefly
        # popping up in its own window when its geometry shifts under the cursor.
        self.type_filter.hide()
        self.search.setVisible(show)
        self.search_toggle.setIcon(self.search_icon if not show else self.close_icon)
        if not show:
            # clear search when closed
            self.search.clear()
            self.refresh_list()
        self._rebuild_filter_row()
        # hide any open popup that might have been triggered by the mouse
        self.type_filter.hidePopup()
        # set a flag so eventFilter can swallow any upcoming show events
        self._suppress_combo = True
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: setattr(self, '_suppress_combo', False))
        # briefly disable the combo so stray press/release events can't open it
        self.type_filter.setEnabled(False)
        QTimer.singleShot(0, lambda: self.type_filter.setEnabled(True))
        # show combo once layout has been rebuilt
        self.type_filter.show()
        if show:
            # delay focusing the search field until after the layout settles
            QTimer.singleShot(0, self.search.setFocus)

    def _tool_icon(self, tool_type: str) -> QIcon:
        filename = TOOL_TYPE_TO_ICON.get(tool_type, DEFAULT_TOOL_ICON)
        path = TOOL_ICONS_DIR / filename
        if not path.exists():
            path = TOOL_ICONS_DIR / DEFAULT_TOOL_ICON
        return QIcon(str(path)) if path.exists() else QIcon()

    def _load_preview_content(self, viewer, stl_path: str | None, label: str | None = None) -> bool:
        if StlPreviewWidget is None or viewer is None or not stl_path:
            return False

        try:
            parsed = json.loads(stl_path)

            if isinstance(parsed, list):
                viewer.load_parts(parsed)
                return True

            if isinstance(parsed, str) and parsed.strip():
                viewer.load_stl(parsed, label=label)
                return True
        except Exception:
            viewer.load_stl(stl_path, label=label)
            return True

        return False

    def _set_preview_button_checked(self, checked: bool):
        self.preview_window_btn.blockSignals(True)
        self.preview_window_btn.setChecked(checked)
        self.preview_window_btn.blockSignals(False)

    def _ensure_detached_preview_dialog(self):
        if self._detached_preview_dialog is not None:
            return

        dialog = QDialog(self)
        dialog.setProperty('detachedPreviewDialog', True)
        dialog.setWindowTitle(self._t('tool_library.preview.window_title', '3D Preview'))
        dialog.resize(620, 820)
        dialog.finished.connect(self._on_detached_preview_closed)
        self._close_preview_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), dialog)
        self._close_preview_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self._close_preview_shortcut.activated.connect(dialog.close)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        controls_host = QWidget(dialog)
        controls_host.setProperty('detachedPreviewToolbar', True)
        controls_host.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        controls_layout = QHBoxLayout(controls_host)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)
        controls_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self._measurement_toggle_btn = QToolButton(controls_host)
        self._measurement_toggle_btn.setCheckable(True)
        self._measurement_toggle_btn.setChecked(self._detached_measurements_enabled)
        self._measurement_toggle_btn.setIconSize(QSize(28, 28))
        self._measurement_toggle_btn.setAutoRaise(True)
        self._measurement_toggle_btn.setProperty('topBarIconButton', True)
        self._measurement_toggle_btn.setFixedSize(36, 36)
        self._update_detached_measurement_toggle_icon(self._measurement_toggle_btn.isChecked())
        self._measurement_toggle_btn.clicked.connect(self._on_detached_measurements_toggled)
        controls_layout.addWidget(self._measurement_toggle_btn)

        measurements_label = QLabel(self._t('tool_library.preview.measurements_label', 'Mittaukset'))
        measurements_label.setProperty('detailHint', True)
        measurements_label.setProperty('detachedPreviewToolbarLabel', True)
        measurements_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        controls_layout.addWidget(measurements_label)

        self._measurement_filter_combo = None
        controls_layout.addStretch(1)
        layout.addWidget(controls_host)

        if StlPreviewWidget is not None:
            self._detached_preview_widget = StlPreviewWidget()
            self._detached_preview_widget.set_control_hint_text(
                self._t(
                    'tool_editor.hint.rotate_pan_zoom',
                    'Rotate: left mouse • Pan: right mouse • Zoom: mouse wheel',
                )
            )
            self._detached_preview_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(self._detached_preview_widget, 1)
        else:
            fallback = QLabel(self._t('tool_library.preview.unavailable', 'Preview component not available.'))
            fallback.setWordWrap(True)
            fallback.setAlignment(Qt.AlignCenter)
            self._detached_preview_widget = None
            fallback.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(fallback, 1)

        self._detached_preview_dialog = dialog
        self._refresh_detached_measurement_controls([])

    def _apply_detached_preview_default_bounds(self):
        if self._detached_preview_dialog is None:
            return
        host_window = self.window()
        if host_window is None:
            return

        host_frame = host_window.frameGeometry()
        if host_frame.width() <= 0 or host_frame.height() <= 0:
            return

        width = max(520, int(host_frame.width() * 0.37))
        width = min(width, 700)
        max_height = max(420, host_frame.height() - 30)
        height = max(600, int(host_frame.height() * 0.86))
        height = min(height, max_height)

        x = host_frame.right() - width + 1
        y = host_frame.bottom() - height + 1
        min_y = host_frame.top() + 30
        if y < min_y:
            y = min_y

        self._detached_preview_dialog.setGeometry(x, y, width, height)

    def _update_detached_measurement_toggle_icon(self, enabled: bool):
        if self._measurement_toggle_btn is None:
            return
        is_enabled = bool(enabled)
        icon_name = 'comment_disable.svg' if is_enabled else 'comment.svg'
        self._measurement_toggle_btn.setIcon(QIcon(str(TOOL_ICONS_DIR / icon_name)))
        tooltip = self._t(
            'tool_library.preview.measurements_hide' if is_enabled else 'tool_library.preview.measurements_show',
            'Piilota mittaukset' if is_enabled else 'Näytä mittaukset',
        )
        self._measurement_toggle_btn.setToolTip(tooltip)

    def _on_detached_preview_closed(self, _result):
        if self._detached_preview_widget is not None:
            self._detached_preview_widget.set_measurement_focus_index(-1)
        self._detached_preview_last_model_key = None
        self._set_preview_button_checked(False)

    def _refresh_detached_measurement_controls(self, overlays):
        if self._measurement_toggle_btn is None:
            return

        names = []
        seen = set()
        for overlay in overlays or []:
            if not isinstance(overlay, dict):
                continue
            name = str(overlay.get('name') or '').strip()
            if not name or name in seen:
                continue
            names.append(name)
            seen.add(name)

        has_measurements = bool(names)
        self._measurement_toggle_btn.setEnabled(has_measurements)

        self._measurement_toggle_btn.blockSignals(True)
        self._measurement_toggle_btn.setChecked(self._detached_measurements_enabled and has_measurements)
        self._measurement_toggle_btn.blockSignals(False)
        self._update_detached_measurement_toggle_icon(self._measurement_toggle_btn.isChecked())
        self._detached_measurement_filter = None

    def _apply_detached_measurement_state(self, overlays):
        if self._detached_preview_widget is None:
            return
        self._detached_preview_widget.set_measurement_overlays(overlays or [])
        self._detached_preview_widget.set_measurements_visible(
            bool(overlays) and self._detached_measurements_enabled
        )
        self._detached_preview_widget.set_measurement_filter(self._detached_measurement_filter)

    def _on_detached_measurements_toggled(self, checked: bool):
        self._detached_measurements_enabled = bool(checked)
        self._update_detached_measurement_toggle_icon(self._detached_measurements_enabled)
        if self._detached_preview_widget is not None:
            self._detached_preview_widget.set_measurements_visible(self._detached_measurements_enabled)

    def _close_detached_preview(self):
        if self._detached_preview_dialog is not None:
            self._detached_preview_dialog.close()
        else:
            self._set_preview_button_checked(False)

    def _sync_detached_preview(self, show_errors: bool = False) -> bool:
        if not self.preview_window_btn.isChecked():
            return False

        if not self.current_tool_id:
            self._close_detached_preview()
            return False

        tool = self._get_selected_tool()
        if not tool:
            self._close_detached_preview()
            return False

        stl_path = tool.get('stl_path')
        if not stl_path:
            if show_errors:
                QMessageBox.information(
                    self,
                    self._t('tool_library.preview.window_title', '3D Preview'),
                    self._t('tool_library.preview.none_assigned_selected', 'The selected tool has no 3D model assigned.'),
                )
            self._close_detached_preview()
            return False

        self._ensure_detached_preview_dialog()
        was_visible = bool(self._detached_preview_dialog and self._detached_preview_dialog.isVisible())
        label = tool.get('description', '').strip() or tool.get('id', '3D Preview')
        raw_model_key = stl_path if isinstance(stl_path, str) else json.dumps(stl_path, ensure_ascii=False, sort_keys=True)
        model_key = (
            int(tool.get('uid')) if str(tool.get('uid', '')).strip().isdigit() else str(tool.get('id') or '').strip(),
            str(raw_model_key or ''),
        )
        loaded = True
        if self._detached_preview_last_model_key != model_key:
            loaded = self._load_preview_content(self._detached_preview_widget, stl_path, label=label)
            if loaded:
                self._detached_preview_last_model_key = model_key
            else:
                self._detached_preview_last_model_key = None
        if not loaded:
            if show_errors:
                QMessageBox.information(
                    self,
                    self._t('tool_library.preview.window_title', '3D Preview'),
                    self._t('tool_library.preview.no_valid_selected', 'No valid 3D model data found for the selected tool.'),
                )
            self._close_detached_preview()
            return False

        overlays = tool.get('measurement_overlays', []) if isinstance(tool, dict) else []
        self._refresh_detached_measurement_controls(overlays)
        self._apply_detached_measurement_state(overlays)

        tool_id = self._tool_id_display_value(tool.get('id', ''))
        self._detached_preview_dialog.setWindowTitle(
            self._t('tool_library.preview.window_title_tool', '3D Preview - {tool_id}', tool_id=tool_id).rstrip(' -')
        )
        if not was_visible:
            self._apply_detached_preview_default_bounds()
            self._detached_preview_dialog.show()
            self._detached_preview_dialog.raise_()
            self._detached_preview_dialog.activateWindow()
        self._set_preview_button_checked(True)
        return True

    def toggle_preview_window(self):
        if self.preview_window_btn.isChecked():
            if not self._sync_detached_preview(show_errors=True):
                self._set_preview_button_checked(False)
            return

        self._close_detached_preview()

    def select_tool_by_id(self, tool_id: str):
        """Navigate the list to the tool with the given id."""
        self.current_tool_id = tool_id.strip()
        self.current_tool_uid = None
        self.refresh_list()
        for row in range(self._tool_model.rowCount()):
            idx = self._tool_model.index(row, 0)
            if idx.data(ROLE_TOOL_ID) == self.current_tool_id:
                self.tool_list.setCurrentIndex(idx)
                self.tool_list.scrollTo(idx)
                break

    def _get_selected_tool(self):
        if self.current_tool_uid is not None:
            tool = self.tool_service.get_tool_by_uid(self.current_tool_uid)
            if tool:
                return tool
        if self.current_tool_id:
            return self.tool_service.get_tool(self.current_tool_id)
        return None

    def refresh_list(self):
        # bail if UI hasn't been built yet
        if not hasattr(self, 'tool_list'):
            return
        tools = self.tool_service.list_tools(
            self.search.text(),
            self.type_filter.currentData() or 'All',
            self._selected_head_filter(),
        )
        if self._master_filter_active:
            tools = [tool for tool in tools if str(tool.get('id', '')).strip() in self._master_filter_ids]
        tools = [tool for tool in tools if self._view_match(tool)]
        self._tool_model.blockSignals(True)
        self._tool_model.clear()
        for tool in tools:
            item = QStandardItem()
            tool_id = tool.get('id', '')
            tool_uid = tool.get('uid')
            item.setData(tool_id, ROLE_TOOL_ID)
            item.setData(tool_uid, ROLE_TOOL_UID)
            item.setData(tool, ROLE_TOOL_DATA)
            item.setData(tool_icon_for_type(tool.get('tool_type', '')), ROLE_TOOL_ICON)
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
            self._tool_model.appendRow(item)
        self._tool_model.blockSignals(False)
        # restore selection
        if self.current_tool_uid is not None:
            for row in range(self._tool_model.rowCount()):
                idx = self._tool_model.index(row, 0)
                if idx.data(ROLE_TOOL_UID) == self.current_tool_uid:
                    self.tool_list.setCurrentIndex(idx)
                    self.tool_list.scrollTo(idx)
                    break
        elif self.current_tool_id:
            for row in range(self._tool_model.rowCount()):
                idx = self._tool_model.index(row, 0)
                if idx.data(ROLE_TOOL_ID) == self.current_tool_id:
                    self.tool_list.setCurrentIndex(idx)
                    self.tool_list.scrollTo(idx)
                    break

        # Force immediate relayout/repaint so head-filter changes are visible
        # without requiring a hover/mouse-move over the list viewport.
        self.tool_list.doItemsLayout()
        self.tool_list.viewport().update()
        self.tool_list.viewport().repaint()

    def _view_match(self, tool: dict) -> bool:
        if self.view_mode == 'holders':
            return bool((tool.get('holder_code', '') or '').strip())

        if self.view_mode == 'inserts':
            return bool((tool.get('cutting_code', '') or '').strip())

        if self.view_mode == 'assemblies':
            support_parts = tool.get('support_parts', [])
            if isinstance(support_parts, str):
                try:
                    support_parts = json.loads(support_parts or '[]')
                except Exception:
                    support_parts = []

            stl_parts = []
            stl_data = tool.get('stl_path', '')
            if isinstance(stl_data, str) and stl_data.strip():
                try:
                    parsed = json.loads(stl_data)
                    stl_parts = parsed if isinstance(parsed, list) else []
                except Exception:
                    stl_parts = []

            return len(support_parts) > 0 or len(stl_parts) > 1

        # home/tools/export pages use full list
        return True

    def toggle_details(self):
        if self._details_hidden:
            if not self.current_tool_id:
                QMessageBox.information(self, self._t('tool_library.message.show_details', 'Show details'), self._t('tool_library.message.select_tool_first', 'Select a tool first.'))
                return
            tool = self._get_selected_tool()
            self.populate_details(tool)
            self.show_details()
        else:
            self.hide_details()

    def show_details(self):
        if self._selector_active:
            self._set_selector_panel_mode('details')
            return
        self._details_hidden = False
        self.detail_container.show()
        self.detail_header_container.show()
        self.toggle_details_btn.setText(self._t('tool_library.details.hide', 'HIDE DETAILS'))
        if not self._last_splitter_sizes:
            total = max(600, self.splitter.width())
            self._last_splitter_sizes = [int(total * 0.62), int(total * 0.38)]
        self.splitter.setSizes(self._last_splitter_sizes)
        self._update_row_type_visibility(False)

    def hide_details(self):
        if self._selector_active:
            self._set_selector_panel_mode('selector')
            return
        self._details_hidden = True
        if self.detail_container.isVisible():
            self._last_splitter_sizes = self.splitter.sizes()
        self.detail_container.hide()
        self.detail_header_container.hide()
        self.toggle_details_btn.setText(self._t('tool_library.details.show', 'SHOW DETAILS'))
        self.splitter.setSizes([1, 0])
        self._update_row_type_visibility(True)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if getattr(obj, 'property', None) and obj.property('elideGroupTitle'):
            if event.type() in (QEvent.Resize, QEvent.Show, QEvent.FontChange):
                self._refresh_elided_group_title(obj)
        if obj is getattr(self, 'type_filter', None) or (
                getattr(self, 'type_filter', None) and obj is self.type_filter.view()):
            # if we are currently suppressing, swallow any show events
            if getattr(self, '_suppress_combo', False) and event.type() in (QEvent.Show, QEvent.ShowToParent):
                return True
        # clear selection when clicking on empty area of the tool list or its viewport
        if obj in (getattr(self, 'tool_list', None),
                   getattr(self, 'tool_list', None) and self.tool_list.viewport()):
            if event.type() == QEvent.MouseButtonPress:
                # coordinate is in viewport space either way
                if not self.tool_list.indexAt(event.pos()).isValid():
                    self._clear_selection()
        return super().eventFilter(obj, event)

    def _refresh_elided_group_title(self, group):
        if group is None or not hasattr(group, 'setTitle'):
            return
        full_title = str(group.property('fullGroupTitle') or group.title() or '').strip()
        if not full_title:
            return
        available = max(12, group.width() - 30)
        elided = QFontMetrics(group.font()).elidedText(full_title, Qt.ElideRight, available)
        group.setTitle(elided)
        group.setToolTip(full_title)

    def _clear_selection(self):
        """Internal helper to clear row selection and reset details."""
        details_were_open = not self._details_hidden
        if hasattr(self, 'tool_list'):
            self.tool_list.selectionModel().clearSelection()
            self.tool_list.setCurrentIndex(QModelIndex())
        self.current_tool_id = None
        self.current_tool_uid = None
        self._update_selection_count_label()
        self.populate_details(None)
        if details_were_open:
            self.hide_details()
        if hasattr(self, 'preview_window_btn') and self.preview_window_btn.isChecked():
            self._close_detached_preview()

    def _selected_tool_uids(self) -> list[int]:
        model = self.tool_list.selectionModel()
        if model is None:
            return []
        indexes = sorted(model.selectedIndexes(), key=lambda idx: idx.row())
        uids: list[int] = []
        for index in indexes:
            uid = index.data(ROLE_TOOL_UID)
            if uid is None:
                continue
            try:
                parsed = int(uid)
            except Exception:
                continue
            if parsed not in uids:
                uids.append(parsed)
        return uids

    def selected_tools_for_setup_assignment(self) -> list[dict]:
        model = self.tool_list.selectionModel()
        if model is None:
            return []
        indexes = sorted(model.selectedIndexes(), key=lambda idx: idx.row())
        payload: list[dict] = []
        for index in indexes:
            tool_id = str(index.data(ROLE_TOOL_ID) or '').strip()
            tool_uid = index.data(ROLE_TOOL_UID)
            try:
                parsed_uid = int(tool_uid) if tool_uid is not None else None
            except Exception:
                parsed_uid = None
            payload.append({
                'tool_id': tool_id,
                'tool_uid': parsed_uid,
            })
        return payload

    def _on_multi_selection_changed(self, _selected, _deselected):
        self._update_selection_count_label()

    def _update_selection_count_label(self):
        count = len(self._selected_tool_uids())
        if count > 1:
            self.selection_count_label.setText(
                self._t('tool_library.selection.count', '{count} selected', count=count)
            )
            self.selection_count_label.show()
            return
        self.selection_count_label.hide()

    @staticmethod
    def _prune_backups(db_path: Path, tag: str, keep: int = 5):
        prefix = f"{db_path.stem}_{tag}_"
        backups = sorted(
            db_path.parent.glob(f"{prefix}*.bak"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for stale in backups[keep:]:
            try:
                stale.unlink()
            except Exception:
                pass

    def _create_db_backup(self, tag: str) -> Path:
        db_path = Path(self.tool_service.db.path)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = db_path.parent / f"{db_path.stem}_{tag}_{timestamp}.bak"
        shutil.copy2(db_path, backup_path)
        self._prune_backups(db_path, tag)
        return backup_path

    def _prompt_batch_cancel_behavior(self) -> str:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(self._t('tool_library.batch.cancel.title', 'Batch edit cancelled'))
        box.setText(
            self._t(
                'tool_library.batch.cancel.body',
                'You stopped editing partway through the batch. Do you want to keep the changes you\'ve already saved, or undo all of them?',
            )
        )
        keep_btn = box.addButton(
            self._t('tool_library.batch.cancel.keep', 'Keep'),
            QMessageBox.AcceptRole,
        )
        undo_btn = box.addButton(
            self._t('tool_library.batch.cancel.undo', 'Undo'),
            QMessageBox.DestructiveRole,
        )
        box.addButton(self._t('common.cancel', 'Cancel'), QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is undo_btn:
            return 'undo'
        if clicked is keep_btn:
            return 'keep'
        return 'keep'

    def _batch_edit_tools(self, uids: list[int]):
        saved_before: list[dict] = []
        total = len(uids)
        for idx, uid in enumerate(uids, 1):
            tool = self.tool_service.get_tool_by_uid(uid)
            if not tool:
                continue
            draft_tool = dict(tool)
            while True:
                dlg = AddEditToolDialog(
                    self,
                    tool=draft_tool,
                    tool_service=self.tool_service,
                    translate=self._t,
                    batch_label=f"{idx}/{total}",
                )
                if dlg.exec() != QDialog.Accepted:
                    if saved_before:
                        action = self._prompt_batch_cancel_behavior()
                        if action == 'undo':
                            for previous in reversed(saved_before):
                                self.tool_service.save_tool(previous, allow_duplicate=True)
                    self.refresh_list()
                    return
                result = self._save_from_dialog(dlg)
                if result == 'saved':
                    saved_before.append(tool)
                    break
                if result == 'retry':
                    draft_tool = dlg.get_tool_data()
                    draft_tool['uid'] = uid
                    continue
                self.refresh_list()
                return
        self.refresh_list()

    def _group_edit_tools(self, uids: list[int]):
        dlg = AddEditToolDialog(
            self,
            tool_service=self.tool_service,
            translate=self._t,
            group_edit_mode=True,
            group_count=len(uids),
        )
        baseline = dlg.get_tool_data()
        if dlg.exec() != QDialog.Accepted:
            return
        edited_data = dlg.get_tool_data()
        changed_fields = {
            key: value
            for key, value in edited_data.items()
            if value != baseline.get(key)
        }
        if not changed_fields:
            QMessageBox.information(
                self,
                self._t('tool_library.group_edit.no_changes_title', 'No changes'),
                self._t('tool_library.group_edit.no_changes_body', 'No fields were changed.'),
            )
            return

        self._create_db_backup('group_edit')
        for uid in uids:
            existing = self.tool_service.get_tool_by_uid(uid)
            if not existing:
                continue
            merged = dict(existing)
            merged.update(changed_fields)
            merged['uid'] = uid
            self.tool_service.save_tool(merged, allow_duplicate=True)
        self.refresh_list()

    def keyPressEvent(self, event):
        """Handle escape key to deselect any selected tool row."""
        from PySide6.QtCore import Qt as _Qt
        if event.key() == _Qt.Key_Escape:
            self._clear_selection()
            return
        super().keyPressEvent(event)

    def _on_type_changed(self, _index):
        # update filter icon based on whether a real filter is active
        active = (self.type_filter.currentData() or 'All') != 'All'
        icon_name = 'filter_off.svg' if active else 'filter_arrow_right.svg'
        self.filter_icon.setIcon(QIcon(str(TOOL_ICONS_DIR / icon_name)))
        if active:
            # apply filter immediately
            self.refresh_list()
        else:
            # if filter cleared programmatically, restore list
            self.refresh_list()

    def _selected_head_filter(self) -> str:
        if self._external_head_filter is not None:
            raw = self._external_head_filter.currentData()
            if raw is not None:
                return str(raw)
            return self._external_head_filter.currentText()
        return self._head_filter_value

    def _localized_tool_type(self, raw_tool_type: str) -> str:
        key = f"tool_library.tool_type.{(raw_tool_type or '').strip().lower().replace('.', '_').replace('/', '_').replace(' ', '_')}"
        return self._t(key, raw_tool_type)

    def _localized_cutting_type(self, raw_cutting_type: str) -> str:
        key = f"tool_library.cutting_type.{(raw_cutting_type or '').strip().lower().replace(' ', '_')}"
        return self._t(key, raw_cutting_type)

    @staticmethod
    def _is_turning_drill_tool_type(raw_tool_type: str) -> bool:
        normalized = (raw_tool_type or '').strip().lower()
        return normalized in {'turn drill', 'turn spot drill', 'turn center drill'}

    @staticmethod
    def _is_mill_tool_type(raw_tool_type: str) -> bool:
        return (raw_tool_type or '').strip() in MILLING_TOOL_TYPES

    def _build_tool_type_filter_items(self):
        current_raw = self.type_filter.currentData() if hasattr(self, 'type_filter') and self.type_filter.count() else 'All'
        if not hasattr(self, 'type_filter'):
            return
        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        self.type_filter.addItem(self._t('tool_library.filter.all', 'All'), 'All')
        for raw_type in ALL_TOOL_TYPES:
            self.type_filter.addItem(self._localized_tool_type(raw_type), raw_type)
        for idx in range(self.type_filter.count()):
            if self.type_filter.itemData(idx) == current_raw:
                self.type_filter.setCurrentIndex(idx)
                break
        if self.type_filter.count() and self.type_filter.currentIndex() < 0:
            self.type_filter.setCurrentIndex(0)
        self.type_filter.blockSignals(False)

    def bind_external_head_filter(self, combo: QWidget | None):
        self._external_head_filter = combo
        self.refresh_list()

    def set_head_filter_value(self, value: str, refresh: bool = True):
        normalized = (value or 'HEAD1/2').strip().upper()
        if normalized not in {'HEAD1/2', 'HEAD1', 'HEAD2'}:
            normalized = 'HEAD1/2'
        self._head_filter_value = normalized
        if refresh:
            self.refresh_list()

    def _clear_filter(self):
        # clicked the icon when filter active -> set back to All
        for idx in range(self.type_filter.count()):
            if self.type_filter.itemData(idx) == 'All':
                self.type_filter.setCurrentIndex(idx)
                break

    def _on_current_changed(self, current: QModelIndex, previous: QModelIndex):
        if not current.isValid():
            self.current_tool_id = None
            self.current_tool_uid = None
            self._update_selection_count_label()
            self.populate_details(None)
            if self.preview_window_btn.isChecked():
                self._close_detached_preview()
            return
        self.current_tool_id = current.data(ROLE_TOOL_ID)
        self.current_tool_uid = current.data(ROLE_TOOL_UID)
        self._update_selection_count_label()
        # if details pane is already visible, refresh its contents
        if not self._details_hidden:
            tool = self._get_selected_tool()
            self.populate_details(tool)
        if self.preview_window_btn.isChecked():
            self._sync_detached_preview(show_errors=False)

    def _on_double_clicked(self, index: QModelIndex):
        self.current_tool_id = index.data(ROLE_TOOL_ID)
        self.current_tool_uid = index.data(ROLE_TOOL_UID)
        if QApplication.keyboardModifiers() & Qt.ControlModifier:
            self.edit_tool()
            return
        # if detail window already open, close it; otherwise open/update
        if not self._details_hidden:
            self.hide_details()
        else:
            self.populate_details(self._get_selected_tool())
            self.show_details()

    # ==============================
    # Detail Panel Construction
    # ==============================
    def _clear_details(self):
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _build_placeholder_details(self):
        card = QFrame()
        card.setProperty('subCard', True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        title = QLabel(self._t('tool_library.section.tool_details', 'Tool details'))
        title.setProperty('detailSectionTitle', True)
        layout.addWidget(title)
        info = QLabel(self._t('tool_library.message.select_tool_for_details', 'Select a tool to view details.'))
        info.setProperty('detailHint', True)
        info.setWordWrap(True)
        layout.addWidget(info)
        preview = QFrame()
        preview.setProperty('diagramPanel', True)
        p = QVBoxLayout(preview)
        p.setContentsMargins(12, 12, 12, 12)
        p.addStretch(1)
        p.addStretch(1)
        layout.addWidget(preview)
        return card

    def populate_details(self, tool):
        self._clear_details()
        if not tool:
            self.detail_layout.addWidget(self._build_placeholder_details())
            return

        support_parts = tool.get('support_parts', []) if isinstance(tool.get('support_parts'), list) else json.loads(tool.get('support_parts', '[]') or '[]')

        card = QFrame()
        card.setProperty('subCard', True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header = QFrame()
        header.setProperty('detailHeader', True)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 14, 14, 12)
        header_layout.setSpacing(4)

        name_label = QLabel(tool.get('description', '').strip() or self._t('tool_library.common.no_description', 'No description'))
        name_label.setProperty('detailHeroTitle', True)
        name_label.setWordWrap(True)
        name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        tool_id_text = self._tool_id_display_value(tool.get('id', '')) or '-'
        id_label = QLabel(tool_id_text)
        id_label.setProperty('detailHeroTitle', True)
        id_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)
        title_row.addWidget(name_label, 1)
        title_row.addWidget(id_label, 0, Qt.AlignRight)

        meta_row = QHBoxLayout()
        badge = QLabel(self._localized_tool_type(tool.get('tool_type', '')))
        badge.setProperty('toolBadge', True)
        meta_row.addWidget(badge, 0, Qt.AlignLeft)
        tool_head = (tool.get('tool_head', 'HEAD1') or 'HEAD1').strip().upper()
        head_badge = QLabel(tool_head)
        head_badge.setProperty('toolBadge', True)
        meta_row.addStretch(1)
        meta_row.addWidget(head_badge, 0, Qt.AlignRight)
        header_layout.addLayout(title_row)
        header_layout.addLayout(meta_row)
        layout.addWidget(header)

        raw_cutting_type = tool.get('cutting_type', 'Insert')
        raw_tool_type = tool.get('tool_type', '')
        turning_drill_type = self._is_turning_drill_tool_type(raw_tool_type)

        # Build the information grid using 6 equal columns.
        # Two-box rows use 3+3 spans; three-box rows use 2+2+2 spans.
        info = QGridLayout()
        info.setHorizontalSpacing(6)
        info.setVerticalSpacing(8)
        info.setColumnStretch(0, 1)
        info.setColumnStretch(1, 1)
        info.setColumnStretch(2, 1)
        info.setColumnStretch(3, 1)

        info.setColumnStretch(4, 1)
        info.setColumnStretch(5, 1)

        angle_value = str(tool.get('drill_nose_angle', ''))
        if not angle_value.strip():
            # Backward compatibility: older records may store point angle in nose_corner_radius.
            angle_value = str(tool.get('nose_corner_radius', ''))

        def _fallback_pair_row(left_label: str, left_value: str, right_label: str, right_value: str) -> None:
            info.addWidget(self._build_detail_field(left_label, left_value), 1, 0, 1, 3, Qt.AlignTop)
            info.addWidget(self._build_detail_field(right_label, right_value), 1, 3, 1, 3, Qt.AlignTop)

        full_row = apply_tool_detail_layout_rules(
            tool=tool,
            tool_head=tool_head,
            raw_tool_type=raw_tool_type,
            raw_cutting_type=raw_cutting_type,
            turning_drill_type=turning_drill_type,
            angle_value=angle_value,
            milling_tool_types=MILLING_TOOL_TYPES,
            turning_tool_types=TURNING_TOOL_TYPES,
            add_two_box_row=lambda row, ll, lv, rl, rv: self._add_two_box_row(info, row, ll, lv, rl, rv),
            add_three_box_row=lambda row, l1, v1, l2, v2, l3, v3: self._add_three_box_row(
                info, row, l1, v1, l2, v2, l3, v3
            ),
            add_fallback_pair_row=_fallback_pair_row,
            translate=self._t,
        )

        # notes field - spans full width
        notes_text = tool.get('notes', tool.get('spare_parts', ''))
        if notes_text:
            notes_field = self._build_detail_field(self._t('tool_library.field.notes', 'Notes'), notes_text, multiline=True)
            info.addWidget(notes_field, full_row, 0, 1, 6)
        layout.addLayout(info)
        layout.addWidget(self._build_components_panel(tool, support_parts))
        layout.addWidget(self._build_preview_panel(tool.get('stl_path')))
        layout.addStretch(1)
        self.detail_layout.addWidget(card)

    def _value_label(self, text):
        lbl = QLabel(text or '-')
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lbl.setProperty('detailValue', True)
        lbl.setMinimumWidth(0)
        lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        return lbl
    
    def _component_toggle_arrow_pixmaps(self):
        cached = getattr(self, '_component_toggle_arrows', None)
        if cached is not None:
            return cached

        canvas_size = 20
        font = self.font()
        font.setPixelSize(16)
        font.setBold(True)

        up_arrow = QPixmap(canvas_size, canvas_size)
        up_arrow.fill(Qt.transparent)

        painter = QPainter(up_arrow)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setFont(font)
        painter.setPen(QColor('#2b3640'))
        painter.drawText(up_arrow.rect(), Qt.AlignCenter, '\u25b2')
        painter.end()

        left_arrow = up_arrow.transformed(QTransform().rotate(-90), Qt.SmoothTransformation)
        self._component_toggle_arrows = (left_arrow, up_arrow)
        return self._component_toggle_arrows

    @staticmethod
    def _component_key(item: dict, fallback_idx: int) -> str:
        explicit = (item.get('component_key') or '').strip()
        if explicit:
            return explicit
        role = (item.get('role') or 'component').strip().lower()
        code = (item.get('code') or '').strip()
        if code:
            return f"{role}:{code}"
        return f"{role}:idx:{fallback_idx}"

    def _legacy_component_candidates(self, tool: dict) -> list[dict]:
        """Build compatibility rows when tool data predates `component_items`."""
        raw_cutting_name = tool.get('cutting_type', '')
        cutting_name = self._localized_cutting_type(raw_cutting_name) if raw_cutting_name else self._t(
            'tool_library.field.cutting_part',
            'Cutting part',
        )
        candidates = [
            {
                'role': 'holder',
                'label': self._t('tool_library.field.holder', 'Holder'),
                'code': tool.get('holder_code', ''),
                'link': (tool.get('holder_link', '') or '').strip(),
                'group': '',
                'component_key': 'holder:' + (tool.get('holder_code', '') or '').strip(),
                'order': 0,
            },
            {
                'role': 'holder',
                'label': self._t('tool_library.field.add_element', 'Add. Element'),
                'code': tool.get('holder_add_element', ''),
                'link': (tool.get('holder_add_element_link', '') or '').strip(),
                'group': '',
                'component_key': 'holder:' + (tool.get('holder_add_element', '') or '').strip(),
                'order': 1,
            },
            {
                'role': 'cutting',
                'label': cutting_name,
                'code': tool.get('cutting_code', ''),
                'link': (tool.get('cutting_link', '') or '').strip(),
                'group': '',
                'component_key': 'cutting:' + (tool.get('cutting_code', '') or '').strip(),
                'order': 2,
            },
            {
                'role': 'cutting',
                'label': self._t('tool_library.field.add_cutting', 'Add. {cutting_type}', cutting_type=cutting_name),
                'code': tool.get('cutting_add_element', ''),
                'link': (tool.get('cutting_add_element_link', '') or '').strip(),
                'group': '',
                'component_key': 'cutting:' + (tool.get('cutting_add_element', '') or '').strip(),
                'order': 3,
            },
        ]
        return [item for item in candidates if (item.get('code') or '').strip()]

    def _normalized_component_items(self, tool: dict) -> list[dict]:
        component_items = tool.get('component_items', [])
        if isinstance(component_items, str):
            try:
                component_items = json.loads(component_items or '[]')
            except Exception:
                component_items = []

        normalized: list[dict] = []
        if isinstance(component_items, list):
            for idx, item in enumerate(component_items):
                if not isinstance(item, dict):
                    continue
                role = (item.get('role') or '').strip().lower()
                if role not in {'holder', 'cutting', 'support'}:
                    continue
                code = (item.get('code') or '').strip()
                if not code:
                    continue
                try:
                    order = int(item.get('order', idx))
                except Exception:
                    order = idx
                normalized.append(
                    {
                        'role': role,
                        'label': (item.get('label') or '').strip(),
                        'code': code,
                        'link': (item.get('link') or '').strip(),
                        'group': (item.get('group') or '').strip(),
                        'component_key': (item.get('component_key') or '').strip(),
                        'order': order,
                    }
                )

        if not normalized:
            normalized.extend(self._legacy_component_candidates(tool))

        normalized.sort(key=lambda entry: int(entry.get('order', 0)))
        return normalized

    @staticmethod
    def _spare_index_by_component(support_parts: list | None) -> dict[str, list[dict]]:
        index: dict[str, list[dict]] = {}
        for part in support_parts or []:
            if isinstance(part, str):
                try:
                    part = json.loads(part)
                except Exception:
                    part = {'name': part, 'code': '', 'link': '', 'component_key': ''}
            if not isinstance(part, dict):
                continue
            part_key = (
                (part.get('component_key') or '').strip()
                or (part.get('component') or '').strip()
                or (part.get('component_code') or '').strip()
            )
            if not part_key:
                continue
            index.setdefault(part_key, []).append(part)
        return index

    def _build_component_row_widget(self, item: dict, display_name: str) -> tuple[QFrame, QLabel, str, str]:
        row_card = QFrame()
        row_card.setProperty('editorFieldCard', True)
        row_layout = QHBoxLayout(row_card)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        button_text = (display_name or '').strip()
        btn = QPushButton(button_text)
        btn.setProperty('panelActionButton', True)
        btn.setProperty('componentCompact', True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(
            (item.get('link') or '').strip()
            or self._t('tool_library.part.no_link', 'No link set for: {name}', name=display_name)
        )
        btn.setMinimumWidth(100)
        fm = QFontMetrics(btn.font())
        required_width = fm.horizontalAdvance(button_text) + 34
        btn.setFixedWidth(max(88, min(360, required_width)))
        btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        btn.clicked.connect(lambda _=False, p=item: self.part_clicked(p))
        row_layout.addWidget(btn, 0)

        raw_code = (item.get('code', '') or '').strip()
        code_lbl = QLabel(raw_code if raw_code else '-')
        code_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        code_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        code_style_default = (
            'background: transparent;'
            'border: none;'
            'padding: 0 2px;'
            'font-size: 11pt;'
            'color: #22303c;'
            'font-weight: 400;'
            'border-bottom: 1px solid transparent;'
        )
        code_style_hover = (
            'background: transparent;'
            'border: none;'
            'padding: 0 2px;'
            'font-size: 11pt;'
            'color: #1f5f9a;'
            'font-weight: 400;'
            'border-bottom: 1px solid #1f5f9a;'
        )
        code_lbl.setStyleSheet(code_style_default)
        row_layout.addWidget(code_lbl, 1)
        return row_card, code_lbl, code_style_default, code_style_hover

    def _build_component_spare_host(self, linked_spares: list[dict]) -> QFrame:
        spare_host = QFrame()
        spare_host.setProperty('editorFieldGroup', True)
        spare_host_layout = QVBoxLayout(spare_host)
        spare_host_layout.setContentsMargins(12, 4, 0, 2)
        spare_host_layout.setSpacing(4)
        spare_host.setVisible(False)

        for spare in linked_spares:
            spare_row = QFrame()
            spare_row.setProperty('editorFieldCard', True)
            spare_row_layout = QHBoxLayout(spare_row)
            spare_row_layout.setContentsMargins(0, 0, 0, 0)
            spare_row_layout.setSpacing(8)

            spare_name = (spare.get('name') or self._t('tool_library.field.part', 'Part')).strip()
            spare_btn = QPushButton(spare_name)
            spare_btn.setProperty('panelActionButton', True)
            spare_btn.setProperty('componentCompact', True)
            spare_btn.setCursor(Qt.PointingHandCursor)
            spare_btn.setToolTip(
                (spare.get('link') or '').strip()
                or self._t('tool_library.part.no_link', 'No link set for: {name}', name=spare_name)
            )
            spare_btn_fm = QFontMetrics(spare_btn.font())
            spare_required_width = spare_btn_fm.horizontalAdvance(spare_name) + 48
            spare_btn.setFixedWidth(max(110, min(360, spare_required_width)))
            spare_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
            spare_btn.clicked.connect(lambda _=False, p=spare: self.part_clicked(p))

            spare_code = (spare.get('code') or '').strip()
            spare_code_lbl = QLabel(spare_code if spare_code else '-')
            spare_code_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            spare_code_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            spare_code_lbl.setStyleSheet(
                'background: transparent;'
                'border: none;'
                'padding: 0 2px;'
                'font-size: 10.5pt;'
                'color: #22303c;'
            )

            spare_row_layout.addWidget(spare_btn, 0)
            spare_row_layout.addWidget(spare_code_lbl, 1)
            spare_host_layout.addWidget(spare_row)
        return spare_host

    def _wire_spare_toggle(
        self,
        *,
        frame: QFrame,
        spare_host: QFrame,
        code_lbl: QLabel,
        arrow_lbl: QLabel,
        arrow_up: QPixmap,
        arrow_left: QPixmap,
        code_style_default: str,
        code_style_hover: str,
    ) -> None:
        def _set_code_hover(hovered: bool):
            code_lbl.setStyleSheet(code_style_hover if hovered else code_style_default)

        def _toggle_spares(_e):
            visible = not spare_host.isVisible()
            spare_host.setVisible(visible)
            arrow_lbl.setPixmap(arrow_up if visible else arrow_left)
            _set_code_hover(False)
            frame.updateGeometry()
            frame.update()

        def _hover_enter(_e):
            _set_code_hover(True)

        def _hover_leave(_e):
            _set_code_hover(False)

        code_lbl.mousePressEvent = _toggle_spares
        arrow_lbl.mousePressEvent = _toggle_spares
        code_lbl.enterEvent = _hover_enter
        code_lbl.leaveEvent = _hover_leave
        arrow_lbl.enterEvent = _hover_enter
        arrow_lbl.leaveEvent = _hover_leave

    def _build_detail_field(self, label_text: str, value_text: str, multiline: bool = False) -> QWidget:
        field_group = create_titled_section(label_text)
        field_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        field_group.setMinimumWidth(0)
        field_group.setProperty('elideGroupTitle', True)
        field_group.setProperty('fullGroupTitle', label_text)
        field_group.installEventFilter(self)
        QTimer.singleShot(0, lambda g=field_group: self._refresh_elided_group_title(g))

        flayout = QVBoxLayout(field_group)
        flayout.setContentsMargins(6, 4, 6, 4)
        flayout.setSpacing(4)

        raw_value = '' if value_text is None else str(value_text)
        if multiline:
            normalized_value = (
                raw_value
                .replace('\r\n', '\n')
                .replace('\r', '\n')
                .replace('\u2028', '\n')
                .replace('\u2029', '\n')
                .replace('\\n', '\n')
            )
            value_edit = QLabel(normalized_value if normalized_value.strip() else '-')
            value_edit.setWordWrap(True)
            value_edit.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value_edit.setFocusPolicy(Qt.NoFocus)
            value_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            value_edit.setMinimumHeight(32)
            value_edit.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            value_edit.setStyleSheet(
                'QLabel {'
                '  background-color: #ffffff;'
                '  border: 1px solid #c8d4e0;'
                '  border-radius: 6px;'
                '  padding: 6px;'
                '  font-size: 10.5pt;'
                '}'
            )
            value_edit.setToolTip('')
        else:
            value_edit = QLineEdit(raw_value if raw_value.strip() else '-')
            value_edit.setReadOnly(True)
            value_edit.setFocusPolicy(Qt.NoFocus)
            value_edit.setCursorPosition(0)
            value_edit.setToolTip(raw_value.strip() or '-')
            value_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        flayout.addWidget(value_edit)
        return field_group

    def _add_two_box_row(
        self,
        info: QGridLayout,
        row: int,
        left_label: str,
        left_value: str,
        right_label: str,
        right_value: str,
    ) -> None:
        info.addWidget(self._build_detail_field(left_label, left_value), row, 0, 1, 3, Qt.AlignTop)
        info.addWidget(self._build_detail_field(right_label, right_value), row, 3, 1, 3, Qt.AlignTop)

    def _add_three_box_row(
        self,
        info: QGridLayout,
        row: int,
        first_label: str,
        first_value: str,
        second_label: str,
        second_value: str,
        third_label: str,
        third_value: str,
    ) -> None:
        info.addWidget(self._build_detail_field(first_label, first_value), row, 0, 1, 2, Qt.AlignTop)
        info.addWidget(self._build_detail_field(second_label, second_value), row, 2, 1, 2, Qt.AlignTop)
        info.addWidget(self._build_detail_field(third_label, third_value), row, 4, 1, 2, Qt.AlignTop)

    # ==============================
    # Detail Panel Sections
    # ==============================
    def _build_components_panel(self, tool, support_parts):
        frame = create_titled_section(self._t('tool_library.section.tool_components', 'Tool components'))
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 6)
        layout.setSpacing(6)

        body_host = QFrame()
        body_host.setObjectName('toolComponentsBodyHost')
        body_host.setStyleSheet(
            'QFrame#toolComponentsBodyHost {'
            '  background-color: #ffffff;'
            '  border: none;'
            '  border-radius: 4px;'
            '}'
        )
        body_layout = QVBoxLayout(body_host)
        body_layout.setContentsMargins(8, 8, 8, 8)
        body_layout.setSpacing(6)

        list_layout = QVBoxLayout()
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(4)
        normalized = self._normalized_component_items(tool)
        spare_index = self._spare_index_by_component(support_parts)

        last_group = None
        for idx, item in enumerate(normalized):
            group = (item.get('group') or '').strip()
            if group != last_group:
                last_group = group
                if group:
                    group_label = QLabel(group)
                    group_label.setProperty('detailFieldKey', True)
                    group_label.setStyleSheet(
                        'background: transparent;'
                        'font-weight: 600; font-size: 9pt; color: #5a6a7a;'
                        'border-bottom: 1px solid #d0d8e0; padding: 4px 0 2px 0;'
                    )
                    list_layout.addWidget(group_label)

            display_name = item.get('label', self._t('tool_library.field.part', 'Part'))
            component_key = self._component_key(item, idx)
            linked_spares = spare_index.get(component_key, [])
            row_card, code_lbl, code_style_default, code_style_hover = self._build_component_row_widget(item, display_name)
            row_layout = row_card.layout()

            if linked_spares:
                arrow_style_default = 'background: transparent; border: none; padding: 0 4px;'
                arrow_left, arrow_up = self._component_toggle_arrow_pixmaps()
                arrow_lbl = QLabel()
                arrow_lbl.setPixmap(arrow_left)
                arrow_lbl.setStyleSheet(arrow_style_default)
                arrow_lbl.setAlignment(Qt.AlignCenter)
                arrow_lbl.setFixedWidth(24)
                arrow_lbl.setCursor(Qt.PointingHandCursor)
                arrow_lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
                row_layout.addWidget(arrow_lbl, 0)
                # Make the whole code area clickable to toggle spares
                code_lbl.setCursor(Qt.PointingHandCursor)

            list_layout.addWidget(row_card)

            if linked_spares:
                spare_host = self._build_component_spare_host(linked_spares)
                self._wire_spare_toggle(
                    frame=frame,
                    spare_host=spare_host,
                    code_lbl=code_lbl,
                    arrow_lbl=arrow_lbl,
                    arrow_up=arrow_up,
                    arrow_left=arrow_left,
                    code_style_default=code_style_default,
                    code_style_hover=code_style_hover,
                )
                list_layout.addWidget(spare_host)

        if not normalized:
            empty_row = QFrame()
            empty_row.setProperty('editorFieldCard', True)
            empty_row_layout = QVBoxLayout(empty_row)
            empty_row_layout.setContentsMargins(0, 0, 0, 0)
            empty_row_layout.setSpacing(0)

            empty_edit = QLineEdit('-')
            empty_edit.setReadOnly(True)
            empty_edit.setFocusPolicy(Qt.NoFocus)
            empty_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            empty_row_layout.addWidget(empty_edit)
            list_layout.addWidget(empty_row)

        body_layout.addLayout(list_layout)
        layout.addWidget(body_host)
        return frame

    def _build_preview_panel(self, stl_path: str | None = None):
        frame = create_titled_section(self._t('tool_library.section.preview', 'Preview'))
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(frame)
        layout.setSpacing(10)
        layout.setContentsMargins(6, 4, 6, 6)

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

        dlay = QVBoxLayout(diagram)
        dlay.setContentsMargins(6, 6, 6, 6)
        dlay.setSpacing(0)

        viewer = StlPreviewWidget() if StlPreviewWidget is not None else None
        if viewer is not None:
            viewer.setStyleSheet('background: transparent; border: none;')
            viewer.set_control_hint_text(
                self._t(
                    'tool_editor.hint.rotate_pan_zoom',
                    'Rotate: left mouse • Pan: right mouse • Zoom: mouse wheel',
                )
            )
        loaded = self._load_preview_content(viewer, stl_path, label='Detail Preview') if viewer is not None else False
        if viewer is not None:
            viewer.setMinimumHeight(260)
            viewer.set_measurement_overlays([])
            viewer.set_measurements_visible(False)

        if loaded:
            dlay.addWidget(viewer, 1)
            viewer.show()
        else:
            txt = QLabel(
                self._t('tool_library.preview.invalid_data', 'No valid 3D model data found.')
                if stl_path else
                self._t('tool_library.preview.none_assigned', 'No 3D model assigned.')
            )
            txt.setWordWrap(True)
            txt.setAlignment(Qt.AlignCenter)
            dlay.addStretch(1)
            dlay.addWidget(txt)
            dlay.addStretch(1)

        layout.addWidget(diagram, 1)
        return frame

    # ==============================
    # Dialogs + CRUD Actions
    # ==============================
    def part_clicked(self, part):
        link = (part.get('link', '') or '').strip()
        if not link:
            QMessageBox.information(
                self,
                self._t('tool_library.part.title', 'Tool component'),
                self._t('tool_library.part.no_link', 'No link set for: {name}', name=part.get('name', self._t('tool_library.field.part', 'Part'))),
            )
            return

        url = QUrl.fromUserInput(link)
        if not url.isValid() or not url.scheme():
            QMessageBox.warning(
                self,
                self._t('tool_library.part.title', 'Tool component'),
                self._t('tool_library.part.invalid_link', 'Invalid link: {link}', link=link),
            )
            return
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(
                self,
                self._t('tool_library.part.title', 'Tool component'),
                self._t('tool_library.part.open_failed', 'Unable to open link: {link}', link=link),
            )

    def _save_from_dialog(self, dlg):
        try:
            data = dlg.get_tool_data()
            source_uid = data.get('uid')
            is_new_tool = source_uid is None

            if is_new_tool and self.tool_service.tcode_exists(data['id'], exclude_uid=data.get('uid')):
                confirm_text = (
                    self._t(
                        'tool_library.warning.duplicate_tcode',
                        'This T-code already exists, want to save the tool anyway?\n\n'
                        'This does not overwrite or replace the existing tool.',
                    )
                )
                if not self._confirm_yes_no(
                    self._t('tool_library.warning.duplicate_tcode_title', 'Duplicate T-code'),
                    confirm_text,
                    danger=False,
                ):
                    return 'retry'

            saved_uid = self.tool_service.save_tool(data, allow_duplicate=True)
            saved_tool = self.tool_service.get_tool_by_uid(saved_uid)
            self.current_tool_uid = saved_uid
            self.current_tool_id = (saved_tool or {}).get('id', data['id'])
            self.refresh_list()
            self.populate_details(saved_tool)
            if self.preview_window_btn.isChecked():
                self._sync_detached_preview(show_errors=False)
            return 'saved'
        except ValueError as exc:
            QMessageBox.warning(self, self._t('tool_library.error.invalid_data', 'Invalid data'), str(exc))
            return 'error'

    def _open_tool_editor(self, tool=None):
        draft_tool = tool
        while True:
            dlg = AddEditToolDialog(self, tool=draft_tool, tool_service=self.tool_service, translate=self._t)
            if dlg.exec() != QDialog.Accepted:
                return
            result = self._save_from_dialog(dlg)
            if result == 'saved':
                return
            if result == 'retry':
                draft_tool = dlg.get_tool_data()
                draft_tool.pop('uid', None)
                continue
            return

    def add_tool(self):
        self._open_tool_editor()

    def edit_tool(self):
        selected_uids = self._selected_tool_uids()
        if not selected_uids:
            QMessageBox.information(
                self,
                self._t('tool_library.action.edit_tool_title', 'Edit tool'),
                self._t('tool_library.message.select_tool_first', 'Select a tool first.'),
            )
            return
        if len(selected_uids) > 1:
            mode = ask_multi_edit_mode(self, len(selected_uids), self._t)
            if mode == 'batch':
                self._batch_edit_tools(selected_uids)
            elif mode == 'group':
                self._group_edit_tools(selected_uids)
            return
        tool = self.tool_service.get_tool_by_uid(selected_uids[0])
        self._open_tool_editor(tool=tool)

    def apply_localization(self, translate=None):
        if translate is not None:
            self._translate = translate
        if hasattr(self, 'toolbar_title_label'):
            self.toolbar_title_label.setText(self.page_title)
        if hasattr(self, 'search'):
            self.search.setPlaceholderText(self._t('tool_library.search.placeholder', 'Tool ID, description, holder or cutting code'))
        if hasattr(self, 'detail_section_label'):
            self.detail_section_label.setText(self._t('tool_library.section.tool_details', 'Tool details'))
        if hasattr(self, 'selector_toggle_btn'):
            if self._selector_active and self._selector_panel_mode == 'selector':
                self.selector_toggle_btn.setText(self._t('tool_library.selector.mode_details', 'DETAILS'))
            else:
                self.selector_toggle_btn.setText(self._t('tool_library.selector.mode_selector', 'SELECTOR'))
        if hasattr(self, 'selector_drop_hint'):
            self.selector_drop_hint.setText(
                self._t(
                    'tool_library.selector.drop_hint',
                    'Drag tools from the catalog to this list and reorder them by dragging.',
                )
            )
        if hasattr(self, 'selector_header_title_label'):
            self.selector_header_title_label.setText(self._t('tool_library.selector.header_title', 'Tool Selector'))
        self._update_selector_context_header()
        self._update_selector_assignments_section_title()
        if hasattr(self, 'module_switch_label'):
            self.module_switch_label.setText(self._t('tool_library.module.switch_to', 'Switch to'))
        if hasattr(self, 'copy_btn'):
            self.copy_btn.setText(self._t('tool_library.action.copy_tool', 'COPY TOOL'))
        if hasattr(self, 'edit_btn'):
            self.edit_btn.setText(self._t('tool_library.action.edit_tool', 'EDIT TOOL'))
        if hasattr(self, 'delete_btn'):
            self.delete_btn.setText(self._t('tool_library.action.delete_tool', 'DELETE TOOL'))
        if hasattr(self, 'add_btn'):
            self.add_btn.setText(self._t('tool_library.action.add_tool', 'ADD TOOL'))
        if hasattr(self, 'preview_window_btn'):
            self.preview_window_btn.setToolTip(self._t('tool_library.preview.toggle', 'Toggle detached 3D preview'))
        if hasattr(self, 'type_filter'):
            self._build_tool_type_filter_items()
        if hasattr(self, 'selector_clear_btn'):
            self.selector_clear_btn.setText(self._t('tool_library.selector.clear', 'Clear'))
        if hasattr(self, 'selector_done_btn'):
            self.selector_done_btn.setText(self._t('tool_library.selector.done', 'DONE'))
        if hasattr(self, 'selector_cancel_btn'):
            self.selector_cancel_btn.setText(self._t('tool_library.selector.cancel', 'CANCEL'))
        if hasattr(self, 'selector_move_up_btn'):
            self.selector_move_up_btn.setToolTip(self._t('tool_library.selector.move_up', 'Move Up'))
        if hasattr(self, 'selector_move_down_btn'):
            self.selector_move_down_btn.setToolTip(self._t('tool_library.selector.move_down', 'Move Down'))
        if hasattr(self, 'selector_remove_btn'):
            self.selector_remove_btn.setToolTip(self._t('tool_library.selector.remove', 'Remove'))
        if hasattr(self, 'selector_comment_btn'):
            self.selector_comment_btn.setToolTip(self._t('tool_library.selector.add_comment', 'Add Comment'))
        if hasattr(self, 'selector_delete_comment_btn'):
            self.selector_delete_comment_btn.setToolTip(self._t('tool_library.selector.delete_comment', 'Delete Comment'))
        self._update_selection_count_label()
        self._refresh_selector_assignment_rows()
        self._update_selector_assignment_buttons()
        self.refresh_list()
        if self.current_tool_id or self.current_tool_uid is not None:
            self.populate_details(self._get_selected_tool())
        else:
            self.populate_details(None)

    def copy_tool(self):
        if not self.current_tool_id:
            QMessageBox.information(
                self,
                self._t('tool_library.action.copy_tool_title', 'Copy tool'),
                self._t('tool_library.message.select_tool_first', 'Select a tool first.'),
            )
            return
        new_id, ok = self._prompt_text(
            self._t('tool_library.action.copy_tool_title', 'Copy tool'),
            self._t('tool_library.prompt.new_tool_id', 'New Tool ID:'),
        )
        if not ok or not new_id.strip():
            return
        new_id_storage = self._tool_id_storage_value(new_id)
        if not new_id_storage:
            QMessageBox.warning(
                self,
                self._t('tool_library.action.copy_tool_title', 'Copy tool'),
                self._t('tool_editor.error.tool_id_required', 'Tool ID is required.'),
            )
            return
        new_desc, _ = self._prompt_text(
            self._t('tool_library.action.copy_tool_title', 'Copy tool'),
            self._t('tool_library.prompt.new_description_optional', 'New description (optional):'),
        )
        allow_duplicate = False
        if self.tool_service.tcode_exists(new_id_storage):
            confirm_text = self._t(
                'tool_library.warning.duplicate_tcode',
                'This T-code already exists, want to save the tool anyway?\n\n'
                'This does not overwrite or replace the existing tool.',
            )
            if not self._confirm_yes_no(
                self._t('tool_library.warning.duplicate_tcode_title', 'Duplicate T-code'),
                confirm_text,
                danger=False,
            ):
                return
            allow_duplicate = True
        try:
            if self.current_tool_uid is not None:
                copied = self.tool_service.copy_tool_by_uid(
                    self.current_tool_uid,
                    new_id_storage,
                    new_desc,
                    allow_duplicate=allow_duplicate,
                )
            else:
                copied = self.tool_service.copy_tool(
                    self.current_tool_id,
                    new_id_storage,
                    new_desc,
                    allow_duplicate=allow_duplicate,
                )
            self.current_tool_uid = copied.get('uid') if isinstance(copied, dict) else None
            self.current_tool_id = (copied.get('id') if isinstance(copied, dict) else '') or new_id_storage
            self.refresh_list()
            self.populate_details(self._get_selected_tool())
        except ValueError as exc:
            QMessageBox.warning(self, self._t('tool_library.action.copy_tool_title', 'Copy tool'), str(exc))

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

    def _confirm_yes_no(self, title: str, text: str, *, danger: bool) -> bool:
        box = QMessageBox(self)
        setup_editor_dialog(box)
        box.setIcon(QMessageBox.Warning if danger else QMessageBox.Question)
        box.setWindowTitle(title)
        main_text = text
        info_text = ''
        if '\n\n' in text:
            main_text, info_text = text.split('\n\n', 1)
        box.setText(main_text)
        if info_text:
            box.setInformativeText(info_text)
            # Style only the secondary line to be subtler.
            box.setStyleSheet(
                '#qt_msgbox_informativelabel { font-style: italic; font-weight: 400; color: #5f6a74; }'
            )
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

        yes_btn = box.button(QMessageBox.Yes)
        no_btn = box.button(QMessageBox.No)
        if yes_btn is not None:
            yes_btn.setText(self._t('common.yes', 'Yes'))
            yes_btn.setProperty('panelActionButton', True)
            yes_btn.setProperty('dangerAction', bool(danger))
            yes_btn.setProperty('primaryAction', not danger)
        if no_btn is not None:
            no_btn.setText(self._t('common.no', 'No'))
            no_btn.setProperty('panelActionButton', True)
            no_btn.setProperty('secondaryAction', True)

        return box.exec() == QMessageBox.Yes

    def delete_tool(self):
        if not self.current_tool_id:
            QMessageBox.information(
                self,
                self._t('tool_library.action.delete_tool_title', 'Delete tool'),
                self._t('tool_library.message.select_tool_first', 'Select a tool first.'),
            )
            return
        if self._confirm_yes_no(
            self._t('tool_library.action.delete_tool_title', 'Delete tool'),
            self._t('tool_library.prompt.delete_tool', 'Delete tool {tool_id}?', tool_id=self.current_tool_id),
            danger=True,
        ):
            if self.current_tool_uid is not None:
                self.tool_service.delete_tool_by_uid(self.current_tool_uid)
            else:
                self.tool_service.delete_tool(self.current_tool_id)
            self.current_tool_id = None
            self.current_tool_uid = None
            self.refresh_list()
            self.populate_details(None)
            if self.preview_window_btn.isChecked():
                self._close_detached_preview()

    def export_excel(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            self._t('tool_library.export.title', 'Export to Excel'),
            str(EXPORT_DEFAULT_PATH),
            self._t('tool_library.export.filter_excel', 'Excel (*.xlsx)'),
        )
        if not path:
            return
        try:
            self.export_service.export_tools(path, self.tool_service.list_tools())
            QMessageBox.information(
                self,
                self._t('tool_library.export.done_title', 'Export'),
                self._t('tool_library.export.done_body', 'Exported to\n{path}', path=path),
            )
        except Exception as exc:
            QMessageBox.critical(self, self._t('tool_library.export.failed_title', 'Export failed'), str(exc))

