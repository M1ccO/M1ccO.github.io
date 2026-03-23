
import json
from PySide6.QtCore import Qt, QSize, QUrl, QTimer
from PySide6.QtGui import QIcon, QDesktopServices, QKeySequence, QShortcut
# import QtSvg so that SVG image support is initialized early
import PySide6.QtSvg  # noqa: F401
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QScrollArea, QSplitter, QVBoxLayout, QWidget, QSizePolicy, QToolButton
)
from config import (
    EXPORT_DEFAULT_PATH,
    ALL_TOOL_TYPES,
    TOOL_TYPE_TO_ICON,
    TOOL_ICONS_DIR,
    DEFAULT_TOOL_ICON,
)
from ui.tool_editor_dialog import AddEditToolDialog
from ui.widgets.common import AutoShrinkLabel, add_shadow, apply_shared_dropdown_style, repolish_widget, styled_list_item_height

# the STL preview widget may live in a separate module; import lazily so the
# rest of the application still runs if the real implementation is missing.
try:
    from ui.stl_preview import StlPreviewWidget
except ImportError:  # pragma: no cover - safe fallback
    StlPreviewWidget = None


# ==============================
# Home Catalog Row Widget
# ==============================
class ToolRowWidget(QFrame):
    def __init__(self, tool: dict, icon: QIcon, view_mode: str = 'home', parent=None, translate=None):
        super().__init__(parent)
        self.tool = tool
        self.view_mode = (view_mode or 'home').lower()
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self.setProperty('toolListCard', True)
        self.setProperty('catalogRowCard', True)
        self.setProperty('selected', False)
        self.setProperty('detailOpen', False)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        # container for the tool name column; stays visible in both full and compact modes
        self.type_wrap = None
        # all non-name column wrappers - hidden only in responsive compact mode
        self._other_wraps: list = []
        # value and header labels collected for responsive font scaling in resizeEvent
        self._val_labels: list = []
        self._head_labels: list = []
        self._name_labels: list = []
        self._col_layouts: list = []
        self._wrappable_head_labels: list = []
        self._compact_breakpoint = 560
        self._icon_only_breakpoint = 185
        self._name_wrap_breakpoint = 560
        self._is_compact = False
        self._is_icon_only = False
        self._details_open_context = False
        self._build_ui(icon)

    @staticmethod
    def _safe_float_text(value) -> str:
        try:
            return f"{float(value or 0):.3f}"
        except Exception:
            return '0.000'

    @staticmethod
    def _parse_json_list(value):
        if isinstance(value, list):
            return value
        if not isinstance(value, str) or not value.strip():
            return []
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []

    def _card_columns(self):
        tool_name = (self.tool.get('description', '') or '').strip() or self._t('tool_library.common.no_description', 'No description')

        if self.view_mode == 'holders':
            return [
                ('tool_id', self._t('tool_library.row.tool_id', 'Tool ID'), self.tool.get('id', ''), 100),
                ('holder_name', self._t('tool_library.row.holder_name', 'Holder name'), (self.tool.get('holder_code', '') or '').strip() or '-', 220),
                ('tool_name', self._t('tool_library.row.tool_name', 'Tool name'), tool_name, 320),
            ]

        if self.view_mode == 'inserts':
            return [
                ('tool_id', self._t('tool_library.row.tool_id', 'Tool ID'), self.tool.get('id', ''), 100),
                ('insert_name', self._t('tool_library.row.insert_name', 'Insert name'), (self.tool.get('cutting_code', '') or '').strip() or '-', 250),
                ('tool_name', self._t('tool_library.row.tool_name', 'Tool name'), tool_name, 320),
            ]

        if self.view_mode == 'assemblies':
            support_parts = self._parse_json_list(self.tool.get('support_parts'))
            stl_parts = self._parse_json_list(self.tool.get('stl_path'))
            return [
                ('tool_id', self._t('tool_library.row.tool_id', 'Tool ID'), self.tool.get('id', ''), 100),
                ('tool_name', self._t('tool_library.row.assembly_name', 'Assembly name'), tool_name, 260),
                ('support_parts', self._t('tool_library.row.support_parts', 'Support parts'), str(len(support_parts)), 130),
                ('model_parts', self._t('tool_library.row.model_parts', '3D parts'), str(len(stl_parts) if stl_parts else 0), 120),
            ]

        return [
            ('tool_id', self._t('tool_library.row.tool_id', 'Tool ID'), self.tool.get('id', ''), 100),
            ('tool_name', self._t('tool_library.row.tool_name', 'Tool name'), tool_name, 270),
            ('geom_x', self._t('tool_library.field.geom_x', 'Geom X'), self._safe_float_text(self.tool.get('geom_x', 0)), 110),
            ('geom_z', self._t('tool_library.field.geom_z', 'Geom Z'), self._safe_float_text(self.tool.get('geom_z', 0)), 110),
            ('radius', self._t('tool_library.field.radius', 'Radius'), self._safe_float_text(self.tool.get('radius', 0)), 95),
            ('nose_corner_radius', self._t('tool_library.field.nose_corner_radius_multiline', 'Nose /\nCorner R'), self._safe_float_text(self.tool.get('nose_corner_radius', 0)), 145),
        ]

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _value(self, text: str) -> QLabel:
        lbl = AutoShrinkLabel(text)
        lbl.setProperty('toolCardValue', True)
        lbl.setProperty('catalogRowValue', True)
        lbl.setAlignment(Qt.AlignCenter)
        return lbl

    def _name_value(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty('toolCardValue', True)
        lbl.setProperty('catalogRowValue', True)
        lbl.setProperty('catalogRowPrimaryValue', True)
        lbl.setProperty('fullText', text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lbl.setWordWrap(True)
        lbl.setMargin(0)
        return lbl

    def _build_ui(self, icon: QIcon):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(10)

        icon_label = QLabel()
        icon_label.setProperty("catalogRowIcon", True)
        # make the label background transparent so the card colour shows through
        icon_label.setStyleSheet("background-color: transparent;")
        pm = icon.pixmap(QSize(40, 40))
        icon_label.setPixmap(pm)
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label, 0, Qt.AlignVCenter)

        # column definitions include a "weight" value used solely for stretch
        cols = self._card_columns()
        for key, title, value, weight in cols:
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(0)
            self._col_layouts.append(col)

            head = QLabel(title)
            head.setProperty('toolCardHeader', True)
            head.setProperty('catalogRowHeader', True)
            head.setAlignment(Qt.AlignCenter)
            head.setWordWrap(True)
            if key in {'tool_name', 'nose_corner_radius'}:
                head.setProperty('catalogRowHeaderWrap', True)
                self._wrappable_head_labels.append(head)

            val = self._name_value(value) if key == 'tool_name' else self._value(value)

            wrap = QWidget()
            wrap.setProperty("toolCardColumn", True)
            wrap.setStyleSheet("background: transparent;")
            wrap.setLayout(col)
            # give every column an expanding policy; the "weight" determines its stretch factor
            wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

            # name column stays visible always; other columns are hidden in compact (detail-open) mode
            if key == 'tool_name':
                self.type_wrap = wrap
            else:
                self._other_wraps.append(wrap)

            # track labels so resizeEvent can scale fonts responsively
            self._val_labels.append(val)
            self._head_labels.append(head)
            if key == 'tool_name':
                self._name_labels.append(val)

            col.addWidget(head)
            col.addWidget(val)
            layout.addWidget(wrap, weight, Qt.AlignVCenter)

        layout.addStretch(1)

    def set_type_visible(self, visible: bool):
        """Track detail-pane state and re-run responsive layout."""
        self._details_open_context = not bool(visible)
        self.setProperty('detailOpen', self._details_open_context)
        repolish_widget(self)
        for lbl in self._val_labels + self._head_labels:
            repolish_widget(lbl)
        self._apply_compact_mode(self.width())
        self._apply_responsive_layout(max(1, self.width()))

    def _apply_compact_mode(self, row_width: int):
        # Avoid entering compact mode during initial size negotiation when width is 0.
        if row_width <= 1:
            compact = False
            icon_only = False
        else:
            compact = row_width < self._compact_breakpoint
            icon_only = row_width < self._icon_only_breakpoint
        if compact == self._is_compact and icon_only == self._is_icon_only:
            return
        self._is_compact = compact
        self._is_icon_only = icon_only
        for w in self._other_wraps:
            w.setVisible(not compact)
        if self.type_wrap is not None:
            self.type_wrap.setVisible(not icon_only)

    def _set_row_responsive_properties(self, narrow: bool, tight: bool, tiny: bool):
        changed = False
        for key, value in (('rowNarrow', narrow), ('rowTight', tight), ('rowTiny', tiny)):
            if bool(self.property(key)) != bool(value):
                self.setProperty(key, bool(value))
                changed = True
        if changed:
            repolish_widget(self)
            for lbl in self._val_labels + self._head_labels:
                repolish_widget(lbl)

    @staticmethod
    def _to_max_two_lines(text: str) -> str:
        raw = (text or '').strip()
        if not raw:
            return raw
        parts = raw.split(' - ', 1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            return f"{parts[0].strip()}\n- {parts[1].strip()}"
        if '-' in raw:
            i = raw.find('-')
            left = raw[:i].strip()
            right = raw[i + 1:].strip()
            if left and right:
                return f"{left}\n- {right}"
        pivot = max(4, len(raw) // 2)
        return f"{raw[:pivot].rstrip()}\n{raw[pivot:].lstrip()}"

    def _apply_responsive_layout(self, width: int):
        lay = self.layout()
        if lay is None:
            return

        if width < 380:
            margins = (4, 2, 4, 2)
            spacing = 6
            v_size, name_size, h_size, col_spacing = 10.5, 10.0, 8.0, 0
        elif width < 560:
            margins = (7, 2, 7, 2)
            spacing = 7
            v_size, name_size, h_size, col_spacing = 11.5, 10.5, 8.6, 0
        else:
            margins = (10, 2, 10, 2)
            spacing = 10
            v_size, name_size, h_size, col_spacing = 12.8, 11.5, 9.4, 0

        if self._details_open_context:
            margins = (max(4, margins[0] - 1), margins[1], max(4, margins[2] - 1), margins[3])
            spacing = max(6, spacing - 1)

        lay.setContentsMargins(*margins)
        lay.setSpacing(spacing)
        for col in self._col_layouts:
            col.setSpacing(col_spacing)

        narrow_threshold = 560 + (40 if self._details_open_context else 0)
        tight_threshold = 430 + (40 if self._details_open_context else 0)
        tiny_threshold = 330 + (30 if self._details_open_context else 0)
        row_narrow = width < narrow_threshold
        row_tight = width < tight_threshold
        row_tiny = width < tiny_threshold
        self._set_row_responsive_properties(row_narrow, row_tight, row_tiny)

        wrap_breakpoint = self._name_wrap_breakpoint + (220 if self._details_open_context else 0)
        wrap_name = self._is_compact or width < wrap_breakpoint
        very_narrow_name = wrap_name and width < 340
        if self.type_wrap is not None:
            self.type_wrap.setMaximumWidth(215 if self._details_open_context and not self._is_compact else 16777215)
        for lbl in self._name_labels:
            full_text = str(lbl.property('fullText') or lbl.text() or '')
            display_text = self._to_max_two_lines(full_text) if wrap_name else full_text
            lbl.setText(display_text)
            lbl.setWordWrap(False)
            wrap_changed = bool(lbl.property('nameWrap')) != bool(wrap_name)
            tiny_changed = bool(lbl.property('nameTiny')) != bool(very_narrow_name)
            if wrap_changed:
                lbl.setProperty('nameWrap', bool(wrap_name))
            if tiny_changed:
                lbl.setProperty('nameTiny', bool(very_narrow_name))
            if wrap_changed or tiny_changed:
                repolish_widget(lbl)

    def resizeEvent(self, event):
        """Tighten margins and reduce font slightly when the row becomes narrow."""
        super().resizeEvent(event)
        w = event.size().width()
        self._apply_compact_mode(w)
        self._apply_responsive_layout(w)


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
        self._details_hidden = True
        self._last_splitter_sizes = None
        self._detached_preview_dialog = None
        self._detached_preview_widget = None
        self._close_preview_shortcut = None
        self._inline_preview_warmup = None
        self._active_db_name = ''
        self._module_switch_callback = None
        self._external_head_filter = None
        self._head_filter_value = 'HEAD1/2'
        self._master_filter_ids: set[str] = set()
        self._master_filter_active = False
        self._build_ui()
        self._warmup_preview_engine()
        self.refresh_list()

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _warmup_preview_engine(self):
        """Pre-create a hidden preview widget so first detail-open doesn't flash."""
        if StlPreviewWidget is None:
            return
        self._inline_preview_warmup = StlPreviewWidget(parent=self)
        self._inline_preview_warmup.hide()

        def _drop_warmup():
            if self._inline_preview_warmup is not None:
                self._inline_preview_warmup.deleteLater()
                self._inline_preview_warmup = None

        # Keep warmup alive long enough for first user interactions.
        QTimer.singleShot(10000, _drop_warmup)

    def _update_row_type_visibility(self, show: bool):
        """Called when the detail panel opens/closes to show or hide the secondary row column.
        """
        for idx in range(self.tool_list.count()):
            itm = self.tool_list.item(idx)
            w = self.tool_list.itemWidget(itm)
            if isinstance(w, ToolRowWidget):
                w.set_type_visible(show)

    def _refresh_row_style(self, widget):
        """Force row and child labels to recompute stylesheet on state changes."""
        if widget is None:
            return
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        for lbl in widget.findChildren(QLabel):
            s = lbl.style()
            s.unpolish(lbl)
            s.polish(lbl)
        widget.update()

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
        # slim down left/right padding to push controls closer to the edge
        self.filter_layout.setContentsMargins(0, 6, 0, 6)
        # reduce spacing between icons/widgets
        self.filter_layout.setSpacing(4)

        self.toolbar_title_label = QLabel(self.page_title)
        self.toolbar_title_label.setProperty('pageTitle', True)
        self.toolbar_title_label.setStyleSheet('padding-right: 8px;')

        # search toggle button - use image assets instead of a unicode glyph
        self.search_toggle = QToolButton()
        self.search_icon = QIcon(str(TOOL_ICONS_DIR / 'search_icon.svg'))
        self.close_icon = QIcon(str(TOOL_ICONS_DIR / 'close_icon.svg'))
        self.search_toggle.setIcon(self.search_icon)
        # slightly larger than before so the glass is visible
        # bump default icon size up a bit
        self.search_toggle.setIconSize(QSize(28, 28))
        self.search_toggle.setCheckable(True)
        self.search_toggle.setAutoRaise(True)
        self.search_toggle.setProperty('topBarIconButton', True)
        # larger overall to give padding around the graphic
        self.search_toggle.setFixedSize(36, 36)
        # give it a name so we can target the icon hover specifically
        self.search_toggle.setObjectName('searchToggle')
        # larger icon on hover will be handled by stylesheet (qproperty-iconSize)
        # (the objectName was set earlier as 'searchToggle')
        # remove any custom event overrides if present
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
        type_popup_view.setMinimumHeight(0)
        type_popup_view.setMaximumHeight(8 * 32)
        type_popup_view.window().setMinimumHeight(0)
        type_popup_view.window().setMaximumHeight(8 * 32 + 8)
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
        left_layout.setContentsMargins(6, 0, 10, 10)
        left_layout.setSpacing(10)

        self.tool_list = QListWidget()
        self.tool_list.setObjectName('toolCatalog')
        self.tool_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.tool_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tool_list.setStyleSheet("QListWidget { outline: none; }")
        self.tool_list.setSpacing(4)
        self.tool_list.currentItemChanged.connect(self.on_current_item_changed)
        self.tool_list.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.tool_list.installEventFilter(self)
        self.tool_list.viewport().installEventFilter(self)
        left_layout.addWidget(self.tool_list, 1)
        self.splitter.addWidget(left_card)

        self.detail_container = QWidget()
        self.detail_container.setContentsMargins(0, 0, 0, 0)
        self.detail_container.setMinimumWidth(400)
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
        self.detail_layout = QVBoxLayout(self.detail_panel)
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_layout.setSpacing(10)
        self.detail_scroll.setWidget(self.detail_panel)
        self.detail_layout.addWidget(self._build_placeholder_details())
        detail_card_layout.addWidget(self.detail_scroll, 1)
        dc_layout.addWidget(self.detail_card, 1)
        self.splitter.addWidget(self.detail_container)
        root.addWidget(self.splitter, 1)

        self.detail_container.hide()
        self.detail_header_container.hide()
        self.splitter.setSizes([1, 0])

        button_bar = QFrame()
        button_bar.setProperty('bottomBar', True)
        button_layout = QHBoxLayout(button_bar)
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
        button_layout.addWidget(self.copy_btn)
        button_layout.addWidget(self.edit_btn)
        button_layout.addWidget(self.delete_btn)
        button_layout.addWidget(self.add_btn)
        root.addWidget(button_bar)

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
        dialog.setWindowTitle(self._t('tool_library.preview.window_title', '3D Preview'))
        dialog.resize(900, 650)
        dialog.finished.connect(self._on_detached_preview_closed)
        self._close_preview_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), dialog)
        self._close_preview_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self._close_preview_shortcut.activated.connect(dialog.close)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(8, 8, 8, 8)

        if StlPreviewWidget is not None:
            self._detached_preview_widget = StlPreviewWidget()
            layout.addWidget(self._detached_preview_widget)
        else:
            fallback = QLabel(self._t('tool_library.preview.unavailable', 'Preview component not available.'))
            fallback.setWordWrap(True)
            fallback.setAlignment(Qt.AlignCenter)
            self._detached_preview_widget = None
            layout.addWidget(fallback)

        self._detached_preview_dialog = dialog

    def _on_detached_preview_closed(self, _result):
        self._set_preview_button_checked(False)

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

        tool = self.tool_service.get_tool(self.current_tool_id)
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
        label = tool.get('description', '').strip() or tool.get('id', '3D Preview')
        loaded = self._load_preview_content(self._detached_preview_widget, stl_path, label=label)
        if not loaded:
            if show_errors:
                QMessageBox.information(
                    self,
                    self._t('tool_library.preview.window_title', '3D Preview'),
                    self._t('tool_library.preview.no_valid_selected', 'No valid 3D model data found for the selected tool.'),
                )
            self._close_detached_preview()
            return False

        tool_id = (tool.get('id') or '').strip()
        self._detached_preview_dialog.setWindowTitle(
            self._t('tool_library.preview.window_title_tool', '3D Preview - {tool_id}', tool_id=tool_id).rstrip(' -')
        )
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
        self.refresh_list()
        for i in range(self.tool_list.count()):
            item = self.tool_list.item(i)
            if item.data(Qt.UserRole) == self.current_tool_id:
                self.tool_list.setCurrentItem(item)
                self.tool_list.scrollToItem(item)
                break

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
        self.tool_list.clear()
        for tool in tools:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, tool.get('id', ''))
            row_widget = ToolRowWidget(
                tool,
                self._tool_icon(tool.get('tool_type', '')),
                view_mode=self.view_mode,
                translate=self._t,
            )
            # ensure the row reflects current detail pane state (older versions may lack the method)
            if hasattr(row_widget, 'set_type_visible'):
                row_widget.set_type_visible(self._details_hidden)
            self.tool_list.addItem(item)
            self.tool_list.setItemWidget(item, row_widget)
            # size the list item to the actual widget so stylesheet min-height applies
            item.setSizeHint(QSize(0, styled_list_item_height(row_widget, self.tool_list.spacing())))
        if self.current_tool_id:
            for idx in range(self.tool_list.count()):
                item = self.tool_list.item(idx)
                if item.data(Qt.UserRole) == self.current_tool_id:
                    self.tool_list.setCurrentItem(item)
                    break

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
            tool = self.tool_service.get_tool(self.current_tool_id)
            self.populate_details(tool)
            self.show_details()
        else:
            self.hide_details()

    def show_details(self):
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
                if self.tool_list.itemAt(event.pos()) is None:
                    self._clear_selection()
        return super().eventFilter(obj, event)

    def _clear_selection(self):
        """Internal helper to clear row selection and reset details."""
        # un-highlight the previously selected widget if any
        current = getattr(self, 'tool_list', None) and self.tool_list.currentItem()
        if current:
            prev_widget = self.tool_list.itemWidget(current)
            if prev_widget is not None:
                prev_widget.setProperty('selected', False)
                self._refresh_row_style(prev_widget)
        if hasattr(self, 'tool_list'):
            self.tool_list.setCurrentRow(-1)
            self.tool_list.clearSelection()
        self.current_tool_id = None
        self.populate_details(None)
        if hasattr(self, 'preview_window_btn') and self.preview_window_btn.isChecked():
            self._close_detached_preview()

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

    def _on_head_filter_changed(self, _text):
        self.refresh_list()

    def _selected_head_filter(self) -> str:
        if self._external_head_filter is not None:
            return self._external_head_filter.currentText()
        return self._head_filter_value

    def _localized_tool_type(self, raw_tool_type: str) -> str:
        key = f"tool_library.tool_type.{(raw_tool_type or '').strip().lower().replace('.', '_').replace('/', '_').replace(' ', '_')}"
        return self._t(key, raw_tool_type)

    def _localized_cutting_type(self, raw_cutting_type: str) -> str:
        key = f"tool_library.cutting_type.{(raw_cutting_type or '').strip().lower().replace(' ', '_')}"
        return self._t(key, raw_cutting_type)

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

    def bind_external_head_filter(self, combo: QComboBox | None):
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

    def on_current_item_changed(self, current, previous):
        # adjust visual highlight on widgets
        if previous is not None:
            prev_widget = self.tool_list.itemWidget(previous)
            if prev_widget is not None:
                prev_widget.setProperty('selected', False)
                self._refresh_row_style(prev_widget)
        if not current:
            self.current_tool_id = None
            self.populate_details(None)
            if self.preview_window_btn.isChecked():
                self._close_detached_preview()
            return
        self.current_tool_id = current.data(Qt.UserRole)
        # highlight new widget
        new_widget = self.tool_list.itemWidget(current)
        if new_widget is not None:
            new_widget.setProperty('selected', True)
            self._refresh_row_style(new_widget)
        # if details pane is already visible, refresh its contents
        if not self._details_hidden:
            tool = self.tool_service.get_tool(self.current_tool_id)
            self.populate_details(tool)
        if self.preview_window_btn.isChecked():
            self._sync_detached_preview(show_errors=False)

    def on_item_double_clicked(self, item):
        self.current_tool_id = item.data(Qt.UserRole)
        if QApplication.keyboardModifiers() & Qt.ControlModifier:
            self.edit_tool()
            return
        # if detail window already open, close it; otherwise open/update
        if not self._details_hidden:
            self.hide_details()
        else:
            self.populate_details(self.tool_service.get_tool(self.current_tool_id))
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

        id_label = QLabel(tool.get('id', '-'))
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

        # helper to create a field widget with key and value
        def build_field(label_text: str, value_text: str) -> QWidget:
            field_frame = QFrame()
            field_frame.setProperty('detailField', True)
            field_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
            flayout = QVBoxLayout(field_frame)
            flayout.setContentsMargins(6, 4, 6, 4)
            flayout.setSpacing(4)
            key_lbl = self._detail_key_label(label_text)
            key_lbl.setWordWrap(False)
            value_lbl = self._value_label(value_text)
            value_lbl.setProperty('detailFieldValue', True)
            flayout.addWidget(key_lbl)
            flayout.addWidget(value_lbl)
            return field_frame

        raw_cutting_type = tool.get('cutting_type', 'Insert')
        cutting_type = self._localized_cutting_type(raw_cutting_type)
        holder_add_element = (tool.get('holder_add_element', '') or '').strip()
        cutting_add_element = (tool.get('cutting_add_element', '') or '').strip()

        # Build the information grid.
        # Row 0: Geom X (left half) | Geom Z (right half)
        # Row 1: Radius (left half) | Nose R / Corner R (right half)
        # Row 2+: full-width code fields stacked one by one
        info = QGridLayout()
        info.setHorizontalSpacing(14)
        info.setVerticalSpacing(8)

        info.addWidget(build_field(self._t('tool_library.field.geom_x', 'Geom X'), str(tool.get('geom_x', ''))), 0, 0, 1, 2, Qt.AlignTop)
        info.addWidget(build_field(self._t('tool_library.field.geom_z', 'Geom Z'), str(tool.get('geom_z', ''))), 0, 2, 1, 2, Qt.AlignTop)
        info.addWidget(build_field(self._t('tool_library.field.radius', 'Radius'), str(tool.get('radius', ''))), 1, 0, 1, 2, Qt.AlignTop)
        info.addWidget(build_field(self._t('tool_library.field.nose_corner_radius', 'Nose R / Corner R'), str(tool.get('nose_corner_radius', ''))), 1, 2, 1, 2, Qt.AlignTop)

        full_row = 2
        info.addWidget(build_field(self._t('tool_library.field.holder_code', 'Holder code'), tool.get('holder_code', '')), full_row, 0, 1, 4, Qt.AlignTop)
        full_row += 1
        if holder_add_element:
            info.addWidget(build_field(self._t('tool_library.field.add_element', 'Add. Element'), holder_add_element), full_row, 0, 1, 4, Qt.AlignTop)
            full_row += 1
        info.addWidget(build_field(self._t('tool_library.field.cutting_code', '{cutting_type} code', cutting_type=cutting_type), tool.get('cutting_code', '')), full_row, 0, 1, 4, Qt.AlignTop)
        full_row += 1
        if cutting_add_element:
            info.addWidget(build_field(self._t('tool_library.field.add_cutting', 'Add. {cutting_type}', cutting_type=cutting_type), cutting_add_element), full_row, 0, 1, 4, Qt.AlignTop)
            full_row += 1
        if raw_cutting_type == 'Drill':
            info.addWidget(build_field(self._t('tool_library.field.nose_angle', 'Nose angle'), str(tool.get('drill_nose_angle', ''))), full_row, 0, 1, 4, Qt.AlignTop)
            full_row += 1
        if raw_cutting_type == 'Mill':
            info.addWidget(build_field(self._t('tool_library.field.cutting_edges', 'Cutting edges'), str(tool.get('mill_cutting_edges', ''))), full_row, 0, 1, 4, Qt.AlignTop)
            full_row += 1

        # notes field - spans full width
        notes_text = tool.get('notes', tool.get('spare_parts', ''))
        if notes_text:
            notes_field = QFrame()
            notes_field.setProperty('detailField', True)
            nlayout = QVBoxLayout(notes_field)
            nlayout.setContentsMargins(6, 4, 6, 4)
            nlayout.setSpacing(4)
            notes_key = self._detail_key_label(self._t('tool_library.field.notes', 'Notes'))
            notes_key.setWordWrap(False)
            notes_val = self._value_label(notes_text)
            notes_val.setProperty('detailFieldValue', True)
            notes_val.setWordWrap(True)
            nlayout.addWidget(notes_key)
            nlayout.addWidget(notes_val)
            info.addWidget(notes_field, full_row, 0, 1, 4)
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
        return lbl
    
    def _detail_key_label(self, text):
        lbl = QLabel(text)
        lbl.setProperty('detailFieldKey', True)
        lbl.setWordWrap(False)
        return lbl

    # ==============================
    # Detail Panel Sections
    # ==============================
    def _build_components_panel(self, tool, support_parts):
        frame = QFrame()
        frame.setProperty('subCard', True)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        title = QLabel(self._t('tool_library.section.tool_components', 'Tool components'))
        title.setProperty('detailSectionTitle', True)
        layout.addWidget(title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        row = 0
        raw_cutting_name = tool.get('cutting_type', '')
        cutting_name = self._localized_cutting_type(raw_cutting_name) if raw_cutting_name else self._t('tool_library.field.cutting_part', 'Cutting part')

        holder_part = {
            'name': self._t('tool_library.field.holder', 'Holder'),
            'code': tool.get('holder_code', ''),
            'link': (tool.get('holder_link', '') or '').strip(),
        }
        btn = QPushButton(holder_part['name'])
        btn.setProperty('assemblyPart', True)
        btn.setProperty('panelActionButton', True)
        btn.clicked.connect(lambda _=False, p=holder_part: self.part_clicked(p))
        grid.addWidget(btn, row, 0)
        grid.addWidget(self._value_label(holder_part['code']), row, 1)
        row += 1

        holder_add_element = (tool.get('holder_add_element', '') or '').strip()
        if holder_add_element:
            holder_extra = {
                'name': self._t('tool_library.field.add_element', 'Add. Element'),
                'code': holder_add_element,
                'link': (tool.get('holder_add_element_link', '') or '').strip(),
            }
            btn = QPushButton(holder_extra['name'])
            btn.setProperty('assemblyPart', True)
            btn.setProperty('panelActionButton', True)
            btn.clicked.connect(lambda _=False, p=holder_extra: self.part_clicked(p))
            grid.addWidget(btn, row, 0)
            grid.addWidget(self._value_label(holder_extra['code']), row, 1)
            row += 1

        cutting_part = {
            'name': cutting_name,
            'code': tool.get('cutting_code', ''),
            'link': (tool.get('cutting_link', '') or '').strip(),
        }
        btn = QPushButton(cutting_part['name'])
        btn.setProperty('assemblyPart', True)
        btn.setProperty('panelActionButton', True)
        btn.clicked.connect(lambda _=False, p=cutting_part: self.part_clicked(p))
        grid.addWidget(btn, row, 0)
        grid.addWidget(self._value_label(cutting_part['code']), row, 1)
        row += 1

        cutting_add_element = (tool.get('cutting_add_element', '') or '').strip()
        if cutting_add_element:
            cutting_extra = {
                'name': self._t('tool_library.field.add_cutting', 'Add. {cutting_type}', cutting_type=cutting_name),
                'code': cutting_add_element,
                'link': (tool.get('cutting_add_element_link', '') or '').strip(),
            }
            btn = QPushButton(cutting_extra['name'])
            btn.setProperty('assemblyPart', True)
            btn.setProperty('panelActionButton', True)
            btn.clicked.connect(lambda _=False, p=cutting_extra: self.part_clicked(p))
            grid.addWidget(btn, row, 0)
            grid.addWidget(self._value_label(cutting_extra['code']), row, 1)
            row += 1

        for part in support_parts:
            if isinstance(part, str):
                try:
                    part = json.loads(part)
                except Exception:
                    part = {'name': part, 'code': '', 'link': ''}
            if not isinstance(part, dict):
                continue
            btn = QPushButton(part.get('name', self._t('tool_library.field.part', 'Part')))
            btn.setProperty('assemblyPart', True)
            btn.setProperty('panelActionButton', True)
            btn.clicked.connect(lambda _=False, p=part: self.part_clicked(p))
            grid.addWidget(btn, row, 0)
            grid.addWidget(self._value_label(part.get('code', '')), row, 1)
            row += 1
        layout.addLayout(grid)
        return frame

    def _build_preview_panel(self, stl_path: str | None = None):
        frame = QFrame()
        frame.setProperty('subCard', True)

        layout = QVBoxLayout(frame)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        title = QLabel(self._t('tool_library.section.preview', 'Preview'))
        title.setProperty('detailSectionTitle', True)
        layout.addWidget(title)

        diagram = QFrame()
        diagram.setProperty('diagramPanel', True)
        diagram.setMinimumHeight(180)

        dlay = QVBoxLayout(diagram)
        dlay.setContentsMargins(14, 14, 14, 14)

        viewer = StlPreviewWidget() if StlPreviewWidget is not None else None
        loaded = self._load_preview_content(viewer, stl_path, label='Detail Preview') if viewer is not None else False

        if loaded:
            dlay.addWidget(viewer, 1)
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

        layout.addWidget(diagram)
        return frame

    # ==============================
    # Dialogs + CRUD Actions
    # ==============================
    def _show_stl_dialog(self, path: str):
        dlg = QDialog(self)
        dlg.setWindowTitle(self._t('tool_library.preview.window_title', '3D Preview'))
        layout = QVBoxLayout(dlg)
        if StlPreviewWidget is not None:
            viewer = StlPreviewWidget()
            if self._load_preview_content(viewer, path, label='3D Preview'):
                layout.addWidget(viewer)
            else:
                fallback = QLabel(
                    self._t('tool_library.preview.no_valid_for_path', 'No valid preview data found for:\n{path}', path=path)
                )
                fallback.setWordWrap(True)
                layout.addWidget(fallback)
        else:
            layout.addWidget(
                QLabel(
                    self._t(
                        'tool_library.preview.unavailable_for_path',
                        'Preview component not available for:\n{path}',
                        path=path,
                    )
                )
            )
        dlg.resize(800, 600)
        dlg.exec()

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
            self.tool_service.save_tool(data)
            self.current_tool_id = data['id']
            self.refresh_list()
            self.populate_details(self.tool_service.get_tool(self.current_tool_id))
        except ValueError as exc:
            QMessageBox.warning(self, self._t('tool_library.error.invalid_data', 'Invalid data'), str(exc))

    def add_tool(self):
        dlg = AddEditToolDialog(self, tool_service=self.tool_service, translate=self._t)
        if dlg.exec() == QDialog.Accepted:
            self._save_from_dialog(dlg)

    def edit_tool(self):
        if not self.current_tool_id:
            QMessageBox.information(
                self,
                self._t('tool_library.action.edit_tool_title', 'Edit tool'),
                self._t('tool_library.message.select_tool_first', 'Select a tool first.'),
            )
            return
        tool = self.tool_service.get_tool(self.current_tool_id)
        dlg = AddEditToolDialog(self, tool=tool, tool_service=self.tool_service, translate=self._t)
        if dlg.exec() == QDialog.Accepted:
            self._save_from_dialog(dlg)

    def apply_localization(self, translate=None):
        if translate is not None:
            self._translate = translate
        if hasattr(self, 'toolbar_title_label'):
            self.toolbar_title_label.setText(self.page_title)
        if hasattr(self, 'search'):
            self.search.setPlaceholderText(self._t('tool_library.search.placeholder', 'Tool ID, description, holder or cutting code'))
        if hasattr(self, 'detail_section_label'):
            self.detail_section_label.setText(self._t('tool_library.section.tool_details', 'Tool details'))
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
        self.refresh_list()
        if self.current_tool_id:
            self.populate_details(self.tool_service.get_tool(self.current_tool_id))
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
        new_id, ok = QInputDialog.getText(
            self,
            self._t('tool_library.action.copy_tool_title', 'Copy tool'),
            self._t('tool_library.prompt.new_tool_id', 'New Tool ID:'),
        )
        if not ok or not new_id.strip():
            return
        new_desc, _ = QInputDialog.getText(
            self,
            self._t('tool_library.action.copy_tool_title', 'Copy tool'),
            self._t('tool_library.prompt.new_description_optional', 'New description (optional):'),
        )
        try:
            self.tool_service.copy_tool(self.current_tool_id, new_id, new_desc)
            self.current_tool_id = new_id.strip()
            self.refresh_list()
            self.populate_details(self.tool_service.get_tool(self.current_tool_id))
        except ValueError as exc:
            QMessageBox.warning(self, self._t('tool_library.action.copy_tool_title', 'Copy tool'), str(exc))

    def delete_tool(self):
        if not self.current_tool_id:
            QMessageBox.information(
                self,
                self._t('tool_library.action.delete_tool_title', 'Delete tool'),
                self._t('tool_library.message.select_tool_first', 'Select a tool first.'),
            )
            return
        answer = QMessageBox.question(
            self,
            self._t('tool_library.action.delete_tool_title', 'Delete tool'),
            self._t('tool_library.prompt.delete_tool', 'Delete tool {tool_id}?', tool_id=self.current_tool_id),
        )
        if answer == QMessageBox.Yes:
            self.tool_service.delete_tool(self.current_tool_id)
            self.current_tool_id = None
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

