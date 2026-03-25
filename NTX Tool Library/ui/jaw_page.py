import numpy as np

from typing import Callable

from PySide6.QtCore import QEvent, QModelIndex, QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPixmap, QStandardItem, QStandardItemModel, QTransform
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
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

from config import TOOL_ICONS_DIR
from ui.jaw_catalog_delegate import JawCatalogDelegate, ROLE_JAW_DATA, ROLE_JAW_ICON, ROLE_JAW_ID, jaw_icon_for_row
from ui.jaw_editor_dialog import AddEditJawDialog


def _load_transparent_icon(path, threshold: int = 220) -> QPixmap:
    """Load a PNG and replace near-white pixels with transparency using numpy."""
    img = QImage(str(path))
    if img.isNull():
        return QPixmap()
    img = img.convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    arr = np.frombuffer(img.constBits(), dtype=np.uint8).copy().reshape((h, w, 4))
    # Format_ARGB32 memory layout on little-endian: [B, G, R, A]
    near_white = (arr[:, :, 2] >= threshold) & (arr[:, :, 1] >= threshold) & (arr[:, :, 0] >= threshold)
    arr[near_white, 3] = 0
    out = QImage(arr.tobytes(), w, h, w * 4, QImage.Format_ARGB32)
    return QPixmap.fromImage(out)


_DEFAULT_JAW_ICON = 'hard_jaw.png'


def _jaw_icon_pixmap(jaw: dict, icon_target_size: QSize) -> QPixmap:
    icon_path = TOOL_ICONS_DIR / _DEFAULT_JAW_ICON
    spindle_side = (jaw.get('spindle_side') or '').strip()
    if icon_path.exists():
        pixmap = _load_transparent_icon(icon_path)
        if spindle_side == 'Sub spindle':
            pixmap = pixmap.transformed(QTransform().scale(-1, 1), Qt.SmoothTransformation)
        return pixmap.scaled(icon_target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return QIcon(str(TOOL_ICONS_DIR / 'jaw_icon.png')).pixmap(icon_target_size)
from ui.stl_preview import StlPreviewWidget
from ui.widgets.common import AutoShrinkLabel, add_shadow, apply_shared_dropdown_style, repolish_widget


CATALOG_CARD_HEIGHT = 74
CATALOG_ITEM_HEIGHT = 78


class JawRowWidget(QFrame):
    def __init__(self, jaw: dict, parent=None, translate=None):
        super().__init__(parent)
        self.jaw = jaw
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self.setProperty('toolListCard', True)
        self.setProperty('catalogRowCard', True)
        self.setProperty('selected', False)
        self._val_labels: list[QLabel] = []
        self._head_labels: list[QLabel] = []
        self._col_layouts: list[QVBoxLayout] = []
        self._build_ui()

    def _card_columns(self):
        dash = '-'
        return [
            ('jaw_id', self._t('jaw_library.row.jaw_id', 'Jaw ID'), self.jaw.get('jaw_id', ''), 180),
            (
                'jaw_type',
                self._t('jaw_library.row.jaw_type', 'Jaw type'),
                self._t(
                    f"jaw_library.jaw_type.{(self.jaw.get('jaw_type') or '').strip().lower().replace(' ', '_')}",
                    self.jaw.get('jaw_type', ''),
                ),
                210,
            ),
            ('diameter', self._t('jaw_library.row.clamping_diameter', 'Clamping diameter'), self.jaw.get('clamping_diameter_text', '') or dash, 190),
            ('length', self._t('jaw_library.row.clamping_length', 'Clamping length'), self.jaw.get('clamping_length', '') or dash, 180),
        ]

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _value(self, text: str) -> QLabel:
        lbl = AutoShrinkLabel(text)
        lbl.setProperty('toolCardValue', True)
        lbl.setProperty('catalogRowValue', True)
        lbl.setAlignment(Qt.AlignCenter)
        return lbl

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(10)

        icon_label = QLabel()
        icon_label.setProperty("catalogRowIcon", True)
        icon_target_size = QSize(40, 40)
        pixmap = _jaw_icon_pixmap(self.jaw, icon_target_size)
        icon_label.setPixmap(pixmap)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet('background-color: transparent;')
        layout.addWidget(icon_label, 0, Qt.AlignVCenter)

        for _key, title, value, weight in self._card_columns():
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(0)
            self._col_layouts.append(col)

            head = QLabel(title)
            head.setProperty('toolCardHeader', True)
            head.setProperty('catalogRowHeader', True)
            head.setAlignment(Qt.AlignCenter)
            head.setWordWrap(True)

            val = self._value(value)

            wrap = QWidget()
            wrap.setProperty('toolCardColumn', True)
            wrap.setStyleSheet('background: transparent;')
            wrap.setLayout(col)
            wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

            col.addWidget(head)
            col.addWidget(val)
            layout.addWidget(wrap, weight, Qt.AlignVCenter)

            self._head_labels.append(head)
            self._val_labels.append(val)

        layout.addStretch(1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = event.size().width()
        lay = self.layout()
        if lay is None:
            return
        if w < 560:
            lay.setContentsMargins(7, 2, 7, 2)
            lay.setSpacing(7)
            v_size, h_size, col_spacing = 11.5, 8.6, 0
        else:
            lay.setContentsMargins(10, 2, 10, 2)
            lay.setSpacing(10)
            v_size, h_size, col_spacing = 12.8, 9.4, 0
        for col in self._col_layouts:
            col.setSpacing(col_spacing)
        for lbl in self._val_labels:
            f = lbl.font()
            f.setPointSizeF(v_size)
            lbl.setFont(f)
        for lbl in self._head_labels:
            f = lbl.font()
            f.setPointSizeF(h_size)
            lbl.setFont(f)


class ResponsiveJawRowWidget(QFrame):
    def __init__(self, jaw: dict, parent=None, translate=None):
        super().__init__(parent)
        self.jaw = jaw
        self._translate = translate or (lambda _key, default=None, **_kwargs: default or '')
        self.setProperty('toolListCard', True)
        self.setProperty('catalogRowCard', True)
        self.setProperty('selected', False)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._val_labels: list[QLabel] = []
        self._head_labels: list[QLabel] = []
        self._col_layouts: list[QVBoxLayout] = []
        self._column_wraps: dict[str, QWidget] = {}
        self._column_values: dict[str, QLabel] = {}
        self._column_texts: dict[str, str] = {}
        self._compact_breakpoint = 620
        self._reduced_breakpoint = 560
        self._single_column_breakpoint = 345
        self._icon_only_breakpoint = 220
        self._icon_label = None
        self._icon_wrap = None
        self._details_open_context = False
        self._build_ui()

    def _card_columns(self):
        dash = '-'
        jaw_type_text = self._t(
            f"jaw_library.jaw_type.{(self.jaw.get('jaw_type') or '').strip().lower().replace(' ', '_')}",
            self.jaw.get('jaw_type', ''),
        )
        return [
            ('jaw_id', self._t('jaw_library.row.jaw_id', 'Jaw ID'), self.jaw.get('jaw_id', ''), 180),
            ('jaw_type', self._t('jaw_library.row.jaw_type', 'Jaw type'), jaw_type_text, 210),
            ('diameter', self._t('jaw_library.row.clamping_diameter_multiline', 'Clamping\ndiameter'), self.jaw.get('clamping_diameter_text', '') or dash, 190),
            ('length', self._t('jaw_library.row.clamping_length_multiline', 'Clamping\nlength'), self.jaw.get('clamping_length', '') or dash, 180),
        ]

    def _t(self, key: str, default: str | None = None, **kwargs) -> str:
        return self._translate(key, default, **kwargs)

    def _value(self, text: str) -> QLabel:
        lbl = AutoShrinkLabel(text)
        lbl.setProperty('toolCardValue', True)
        lbl.setProperty('catalogRowValue', True)
        lbl.setAlignment(Qt.AlignCenter)
        return lbl

    @staticmethod
    def _split_responsive_token(text: str) -> str:
        value = (text or '').strip()
        if not value or len(value) <= 8:
            return value
        if '-' in value:
            pivot = value.find('-') + 1
            if 1 < pivot < len(value):
                return f"{value[:pivot]}\n{value[pivot:]}"
        pivot = max(4, len(value) // 2)
        return f"{value[:pivot]}\n{value[pivot:]}"

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(10)

        icon_label = QLabel()
        icon_label.setProperty("catalogRowIcon", True)
        icon_target_size = QSize(40, 40)
        pixmap = _jaw_icon_pixmap(self.jaw, icon_target_size)
        icon_label.setPixmap(pixmap)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet('background-color: transparent;')
        self._icon_label = icon_label
        icon_wrap = QWidget()
        icon_wrap.setStyleSheet('background-color: transparent;')
        icon_wrap_layout = QHBoxLayout(icon_wrap)
        icon_wrap_layout.setContentsMargins(0, 0, 0, 0)
        icon_wrap_layout.setSpacing(0)
        icon_wrap_layout.addStretch(1)
        icon_wrap_layout.addWidget(icon_label, 0, Qt.AlignVCenter)
        icon_wrap_layout.addStretch(1)
        icon_wrap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self._icon_wrap = icon_wrap
        layout.addWidget(icon_wrap, 0, Qt.AlignVCenter)

        for key, title, value, weight in self._card_columns():
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(0)
            self._col_layouts.append(col)

            head = QLabel(title)
            head.setProperty('toolCardHeader', True)
            head.setProperty('catalogRowHeader', True)
            head.setAlignment(Qt.AlignCenter)
            head.setWordWrap(True)
            if key in {'diameter', 'length'}:
                head.setProperty('catalogRowHeaderWrap', True)

            val = self._value(value)

            wrap = QWidget()
            wrap.setProperty('toolCardColumn', True)
            wrap.setStyleSheet('background: transparent;')
            wrap.setLayout(col)
            wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self._column_wraps[key] = wrap
            self._column_values[key] = val
            self._column_texts[key] = value

            col.addWidget(head)
            col.addWidget(val)
            layout.addWidget(wrap, weight, Qt.AlignVCenter)

            self._head_labels.append(head)
            self._val_labels.append(val)

        layout.addStretch(1)

    def _apply_column_visibility(self, width: int):
        if width <= 1:
            visible_keys = {'jaw_id', 'jaw_type', 'diameter', 'length'}
        elif width < self._single_column_breakpoint:
            visible_keys = {'jaw_id'}
        elif width < self._reduced_breakpoint:
            visible_keys = {'jaw_id', 'jaw_type', 'diameter'}
        else:
            visible_keys = {'jaw_id', 'jaw_type', 'diameter', 'length'}

        for key, wrap in self._column_wraps.items():
            wrap.setVisible(key in visible_keys)

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

    def _apply_responsive_layout(self, width: int):
        lay = self.layout()
        if lay is None:
            return

        single_column_mode = width < self._single_column_breakpoint
        icon_only_mode = width < self._icon_only_breakpoint
        jaw_id_wrap_mode = (width < 260) and not icon_only_mode
        row_narrow = width < 560
        row_tight = width < 430
        row_tiny = width < 330
        self._set_row_responsive_properties(row_narrow, row_tight, row_tiny)

        if single_column_mode:
            lay.setContentsMargins(8, 2, 8, 2)
            lay.setSpacing(4)
            col_spacing = 0
        elif width < 520:
            lay.setContentsMargins(7, 2, 7, 2)
            lay.setSpacing(7)
            col_spacing = 0
        else:
            lay.setContentsMargins(10, 2, 10, 2)
            lay.setSpacing(10)
            col_spacing = 0

        self._apply_column_visibility(width)

        jaw_id = self._column_values.get('jaw_id')
        jaw_id_wrap = self._column_wraps.get('jaw_id')
        jaw_id_visible = bool(jaw_id_wrap.isVisible()) if jaw_id_wrap is not None else False
        if jaw_id is not None and jaw_id_visible:
            jaw_id.setText(self._split_responsive_token(self._column_texts.get('jaw_id', '')) if jaw_id_wrap_mode else self._column_texts.get('jaw_id', ''))
            jaw_id.setWordWrap(jaw_id_wrap_mode)
            jaw_id.setMinimumHeight(36 if jaw_id_wrap_mode else 28)
            jaw_id.setMaximumHeight(36 if jaw_id_wrap_mode else 28)
            wrap_changed = bool(jaw_id.property('nameWrap')) != bool(jaw_id_wrap_mode)
            tiny_changed = bool(jaw_id.property('nameTiny')) != bool(jaw_id_wrap_mode)
            if wrap_changed:
                jaw_id.setProperty('nameWrap', bool(jaw_id_wrap_mode))
            if tiny_changed:
                jaw_id.setProperty('nameTiny', bool(jaw_id_wrap_mode))
            if wrap_changed or tiny_changed:
                repolish_widget(jaw_id)
        elif jaw_id is not None:
            jaw_id.setText(self._column_texts.get('jaw_id', ''))
            jaw_id.setWordWrap(False)
            if bool(jaw_id.property('nameWrap')) or bool(jaw_id.property('nameTiny')):
                jaw_id.setProperty('nameWrap', False)
                jaw_id.setProperty('nameTiny', False)
                repolish_widget(jaw_id)

        for col in self._col_layouts:
            col.setSpacing(col_spacing)

        if self._icon_label is not None:
            if icon_only_mode:
                self._icon_label.setFixedSize(36, 36)
            else:
                self._icon_label.setFixedSize(40, 40)

        if self._icon_wrap is not None:
            if icon_only_mode:
                self._icon_wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                self._icon_wrap.setMinimumWidth(0)
                self._icon_wrap.setMaximumWidth(16777215)
            else:
                self._icon_wrap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
                self._icon_wrap.setFixedWidth(48)

    def set_detail_context(self, details_hidden: bool):
        self._details_open_context = not bool(details_hidden)
        self._apply_responsive_layout(max(1, self.width()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout(event.size().width())


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

        filter_frame = QFrame()
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

        self._rebuild_filter_row()
        root.addWidget(filter_frame)

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

        list_card = QFrame()
        list_card.setProperty('catalogShell', True)
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(10)

        self.jaw_list = QListView()
        self.jaw_list.setObjectName('toolCatalog')
        self.jaw_list.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.jaw_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.jaw_list.setSelectionMode(QListView.SingleSelection)
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
        self.jaw_list.doubleClicked.connect(self.on_item_double_clicked)
        list_layout.addWidget(self.jaw_list, 1)

        self.splitter.addWidget(list_card)

        self.detail_container = QWidget()
        self.detail_container.setMinimumWidth(280)
        detail_layout = QVBoxLayout(self.detail_container)
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
        self.splitter.addWidget(self.detail_container)

        self.detail_container.hide()
        self.detail_header_container.hide()
        self.splitter.setSizes([1, 0])

        content.addWidget(self.splitter, 1)
        root.addLayout(content, 1)

        bar_bottom = QFrame()
        bar_bottom.setProperty('bottomBar', True)
        actions = QHBoxLayout(bar_bottom)
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
        self.module_toggle_btn.clicked.connect(self._on_module_switch_clicked)

        actions.addWidget(self.module_switch_label, 0, Qt.AlignLeft | Qt.AlignVCenter)
        actions.addWidget(self.module_toggle_btn, 0, Qt.AlignLeft | Qt.AlignVCenter)
        actions.addStretch(1)
        actions.addWidget(self.add_btn)
        actions.addWidget(self.edit_btn)
        actions.addWidget(self.delete_btn)
        actions.addWidget(self.copy_btn)
        root.addWidget(bar_bottom)

        self._set_view_mode('all', refresh=False)

    def _on_module_switch_clicked(self):
        if callable(self._module_switch_callback):
            self._module_switch_callback()

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
        if obj in (getattr(self, 'jaw_list', None),
                   getattr(self, 'jaw_list', None) and self.jaw_list.viewport()):
            if event.type() == QEvent.MouseButtonPress:
                if not self.jaw_list.indexAt(event.pos()).isValid():
                    self._clear_selection()
        return super().eventFilter(obj, event)

    def _clear_selection(self):
        if hasattr(self, 'jaw_list'):
            self.jaw_list.selectionModel().clearSelection()
            self.jaw_list.setCurrentIndex(QModelIndex())
        self.current_jaw_id = None
        self.populate_details(None)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._clear_selection()
            return
        super().keyPressEvent(event)

    def _clear_details(self):
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _split_used_in_works(self, value: str) -> list[str]:
        return [p.strip() for p in (value or '').split(',') if p.strip()]

    def populate_details(self, jaw):
        self._clear_details()

        if not jaw:
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
            p = QVBoxLayout(placeholder)
            p.setContentsMargins(12, 12, 12, 12)
            p.addStretch(1)
            p.addStretch(1)
            layout.addWidget(placeholder)
            self.detail_layout.addWidget(card)
            self.detail_layout.addStretch(1)
            return

        card = QFrame()
        card.setProperty('subCard', True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header
        header = QFrame()
        header.setProperty('detailHeader', True)
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(14, 14, 14, 12)
        h_layout.setSpacing(4)
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
        h_layout.addLayout(title_row)
        h_layout.addLayout(badge_row)
        layout.addWidget(header)

        # detailField grid â€” same card-box style as Tool Library
        def build_field(label_text, value_text):
            field_frame = QFrame()
            field_frame.setProperty('detailField', True)
            field_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
            fl = QVBoxLayout(field_frame)
            fl.setContentsMargins(6, 4, 6, 4)
            fl.setSpacing(4)
            klbl = QLabel(label_text)
            klbl.setProperty('detailFieldKey', True)
            klbl.setWordWrap(False)
            vlbl = QLabel(value_text if value_text else '-')
            vlbl.setProperty('detailValue', True)
            vlbl.setProperty('detailFieldValue', True)
            vlbl.setWordWrap(True)
            vlbl.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            vlbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            fl.addWidget(klbl)
            fl.addWidget(vlbl)
            return field_frame

        def build_used_in_works_field(value_text: str):
            field_frame = QFrame()
            field_frame.setProperty('detailField', True)
            field_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
            fl = QVBoxLayout(field_frame)
            fl.setContentsMargins(6, 4, 6, 4)
            fl.setSpacing(4)

            klbl = QLabel(self._t('jaw_library.field.used_in_works', 'Used in works:'))
            klbl.setProperty('detailFieldKey', True)
            klbl.setWordWrap(False)
            fl.addWidget(klbl)

            works = self._split_used_in_works(value_text)
            if not works:
                empty = QLabel('-')
                empty.setProperty('detailValue', True)
                empty.setProperty('detailFieldValue', True)
                empty.setWordWrap(True)
                empty.setAlignment(Qt.AlignLeft | Qt.AlignTop)
                empty.setTextInteractionFlags(Qt.TextSelectableByMouse)
                fl.addWidget(empty)
                return field_frame

            for idx, work in enumerate(works):
                value = QLabel(work)
                value.setProperty('detailValue', True)
                value.setProperty('detailFieldValue', True)
                value.setWordWrap(True)
                value.setAlignment(Qt.AlignLeft | Qt.AlignTop)
                value.setTextInteractionFlags(Qt.TextSelectableByMouse)
                fl.addWidget(value)
                if idx < len(works) - 1:
                    sep = QFrame()
                    sep.setFrameShape(QFrame.HLine)
                    sep.setFrameShadow(QFrame.Plain)
                    sep.setStyleSheet('QFrame { color: #D8D8D8; background-color: #D8D8D8; border: none; min-height: 1px; max-height: 1px; }')
                    fl.addWidget(sep)

            return field_frame

        # Base two-column field matrix.
        pairs = [
            (self._t('jaw_library.field.jaw_id', 'Jaw ID'), jaw.get('jaw_id', '')),
            (
                self._t('jaw_library.field.spindle_side', 'Spindle side'),
                self._localized_spindle_side(jaw.get('spindle_side', '')),
            ),
            (self._t('jaw_library.field.clamping_diameter', 'Clamping diameter'), jaw.get('clamping_diameter_text', '')),
            (self._t('jaw_library.field.clamping_length', 'Clamping length'), jaw.get('clamping_length', '')),
            (self._t('jaw_library.field.turning_ring', 'Turning ring'), jaw.get('turning_washer', '')),
            (self._t('jaw_library.field.last_modified', 'Last modified'), jaw.get('last_modified', '')),
        ]

        info = QGridLayout()
        info.setHorizontalSpacing(14)
        info.setVerticalSpacing(8)
        total       = len(pairs)
        left_count  = (total + 1) // 2
        right_count = total - left_count
        for i in range(left_count):
            info.addWidget(build_field(*pairs[i]), i, 0, 1, 2, Qt.AlignTop)
        for j in range(right_count):
            info.addWidget(build_field(*pairs[left_count + j]), j, 2, 1, 2, Qt.AlignTop)

        used_in_works_row = max(left_count, right_count)
        used_in_works_field = build_used_in_works_field(jaw.get('used_in_work', ''))
        info.addWidget(used_in_works_field, used_in_works_row, 0, 1, 4, Qt.AlignTop)

        notes_text = (jaw.get('notes', '') or '').strip()
        if notes_text:
            notes_field = QFrame()
            notes_field.setProperty('detailField', True)
            nl = QVBoxLayout(notes_field)
            nl.setContentsMargins(6, 4, 6, 4)
            nl.setSpacing(4)
            nk = QLabel(self._t('jaw_library.field.notes', 'Notes'))
            nk.setProperty('detailFieldKey', True)
            nk.setWordWrap(False)
            nv = QLabel(notes_text)
            nv.setProperty('detailValue', True)
            nv.setProperty('detailFieldValue', True)
            nv.setWordWrap(True)
            nv.setTextInteractionFlags(Qt.TextSelectableByMouse)
            nl.addWidget(nk)
            nl.addWidget(nv)
            info.addWidget(notes_field, used_in_works_row + 1, 0, 1, 4, Qt.AlignTop)

        layout.addLayout(info)

        # Preview panel â€” diagramPanel wrapper matches Tool Library style
        preview_card = QFrame()
        preview_card.setProperty('subCard', True)
        p_layout = QVBoxLayout(preview_card)
        p_layout.setContentsMargins(12, 12, 12, 12)
        p_layout.setSpacing(10)
        p_title = QLabel(self._t('tool_library.section.preview', 'Preview'))
        p_title.setProperty('detailSectionTitle', True)
        p_layout.addWidget(p_title)

        diagram = QFrame()
        diagram.setProperty('diagramPanel', True)
        diagram.setMinimumHeight(180)
        d_layout = QVBoxLayout(diagram)
        d_layout.setContentsMargins(14, 14, 14, 14)

        stl_path = jaw.get('stl_path', '')
        if stl_path:
            viewer = StlPreviewWidget()
            viewer.load_stl(stl_path, label=jaw.get('jaw_id', self._t('jaw_library.preview.jaw_label', 'Jaw')))
            # Apply jaw-specific saved preview orientation
            plane = (jaw.get('preview_plane', '') or 'XZ').strip()
            if plane not in ('XZ', 'XY', 'YZ'):
                plane = 'XZ'
            viewer.set_alignment_plane(plane)
            for axis, key in (('x', 'preview_rot_x'), ('y', 'preview_rot_y'), ('z', 'preview_rot_z')):
                deg = int(jaw.get(key, 0) or 0) % 360
                if deg:
                    viewer.rotate_model(axis, deg)
            d_layout.addWidget(viewer, 1)
        else:
            txt = QLabel(self._t('tool_library.preview.none_assigned', 'No 3D model assigned.'))
            txt.setProperty('detailHint', True)
            txt.setAlignment(Qt.AlignCenter)
            d_layout.addStretch(1)
            d_layout.addWidget(txt)
            d_layout.addStretch(1)

        p_layout.addWidget(diagram)
        layout.addWidget(preview_card)
        layout.addStretch(1)
        self.detail_layout.addWidget(card)

    def _refresh_row_style(self, widget):
        if widget is None:
            return
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()

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
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
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
        self._details_hidden = False
        self.detail_container.show()
        self.detail_header_container.show()
        if not self._last_splitter_sizes:
            total = max(600, self.splitter.width())
            self._last_splitter_sizes = [int(total * 0.62), int(total * 0.38)]
        self.splitter.setSizes(self._last_splitter_sizes)
        self.refresh_list()

    def hide_details(self):
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
            self.populate_details(None)
            return

        self.current_jaw_id = current.data(ROLE_JAW_ID)

        if not self._details_hidden:
            jaw = self.jaw_service.get_jaw(self.current_jaw_id)
            self.populate_details(jaw)

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

    def _save_from_dialog(self, dlg):
        try:
            data = dlg.get_jaw_data()
            self.jaw_service.save_jaw(data)
            self.current_jaw_id = data['jaw_id']
            self.refresh_list()
            self.populate_details(self.jaw_service.get_jaw(self.current_jaw_id))
        except ValueError as exc:
            QMessageBox.warning(self, self._t('tool_library.error.invalid_data', 'Invalid data'), str(exc))

    def add_jaw(self):
        dlg = AddEditJawDialog(self, translate=self._t)
        if dlg.exec() == QDialog.Accepted:
            self._save_from_dialog(dlg)

    def edit_jaw(self):
        if not self.current_jaw_id:
            QMessageBox.information(
                self,
                self._t('jaw_library.action.edit_jaw', 'Edit jaw'),
                self._t('jaw_library.message.select_jaw_first', 'Select a jaw first.'),
            )
            return
        jaw = self.jaw_service.get_jaw(self.current_jaw_id)
        dlg = AddEditJawDialog(self, jaw=jaw, translate=self._t)
        if dlg.exec() == QDialog.Accepted:
            self._save_from_dialog(dlg)

    def delete_jaw(self):
        if not self.current_jaw_id:
            QMessageBox.information(
                self,
                self._t('jaw_library.action.delete_jaw', 'Delete jaw'),
                self._t('jaw_library.message.select_jaw_first', 'Select a jaw first.'),
            )
            return
        answer = QMessageBox.question(
            self,
            self._t('jaw_library.action.delete_jaw', 'Delete jaw'),
            self._t('jaw_library.message.delete_jaw_prompt', 'Delete jaw {jaw_id}?', jaw_id=self.current_jaw_id),
        )
        if answer != QMessageBox.Yes:
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
        dlg = QInputDialog(self)
        dlg.setWindowTitle(title)
        dlg.setLabelText(label)
        dlg.setTextValue(initial)
        dlg.setInputMode(QInputDialog.TextInput)
        dlg.setOkButtonText(self._t('common.ok', 'OK'))
        dlg.setCancelButtonText(self._t('common.cancel', 'Cancel'))

        # Ensure copy dialogs match panel button styling.
        for btn in dlg.findChildren(QPushButton):
            btn.setProperty('panelActionButton', True)

        accepted = dlg.exec() == QDialog.Accepted
        return dlg.textValue(), accepted

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
        self.refresh_list()
        if self.current_jaw_id:
            self.populate_details(self.jaw_service.get_jaw(self.current_jaw_id))
        else:
            self.populate_details(None)

