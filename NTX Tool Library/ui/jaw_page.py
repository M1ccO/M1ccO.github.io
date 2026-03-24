from typing import Callable

from PySide6.QtCore import QEvent, QModelIndex, QSize, Qt
from PySide6.QtGui import QIcon, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
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

from config import TOOL_ICONS_DIR
from ui.jaw_catalog_delegate import (
    JawCatalogDelegate,
    ROLE_JAW_DATA,
    ROLE_JAW_ICON,
    ROLE_JAW_ID,
    jaw_icon_for_row,
)
from ui.jaw_editor_dialog import AddEditJawDialog
from ui.stl_preview import StlPreviewWidget
from ui.widgets.common import add_shadow, apply_shared_dropdown_style

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

    @staticmethod
    def _norm_id(value) -> str:
        return str(value or '').strip().lower()

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
        self.filter_layout.setContentsMargins(0, 6, 0, 6)
        self.filter_layout.setSpacing(4)

        self.toolbar_title_label = QLabel(self._t('tool_library.module.jaws', 'JAWS'))
        self.toolbar_title_label.setProperty('pageTitle', True)
        self.toolbar_title_label.setStyleSheet('padding-right: 8px;')

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
        list_layout.setContentsMargins(6, 0, 10, 10)
        list_layout.setSpacing(10)

        self.jaw_list = QListView()
        self.jaw_list.setObjectName('toolCatalog')
        self.jaw_list.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.jaw_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.jaw_list.setSelectionMode(QListView.SingleSelection)
        self.jaw_list.setMouseTracking(True)
        self.jaw_list.setUniformItemSizes(True)
        self.jaw_list.setStyleSheet(
            "QListView#toolCatalog { background-color: rgba(205, 212, 238, 0.97);"
            " border: none; outline: none; padding: 8px; }"
            " QListView#toolCatalog::item { background: transparent; border: none; }"
        )
        self.jaw_list.setSpacing(4)
        self._jaw_model = QStandardItemModel(self)
        self.jaw_list.setModel(self._jaw_model)
        self._jaw_delegate = JawCatalogDelegate(parent=self.jaw_list, translate=self._t)
        self.jaw_list.setItemDelegate(self._jaw_delegate)
        self.jaw_list.installEventFilter(self)
        self.jaw_list.viewport().installEventFilter(self)
        self.jaw_list.selectionModel().currentChanged.connect(self._on_current_changed)
        self.jaw_list.doubleClicked.connect(self._on_double_clicked)
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
        self.detail_panel.setMinimumWidth(0)
        self.detail_panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
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
        for btn in [self.edit_btn, self.delete_btn, self.add_btn]:
            btn.setProperty('panelActionButton', True)
        self.delete_btn.setProperty('dangerAction', True)
        self.add_btn.setProperty('primaryAction', True)

        self.edit_btn.clicked.connect(self.edit_jaw)
        self.delete_btn.clicked.connect(self.delete_jaw)
        self.add_btn.clicked.connect(self.add_jaw)

        self.module_switch_label = QLabel(self._t('tool_library.module.switch_to', 'Switch to'))
        self.module_switch_label.setProperty('pageSubtitle', True)
        self.module_toggle_btn = QPushButton(self._t('tool_library.module.tools', 'TOOLS'))
        self.module_toggle_btn.setProperty('panelActionButton', True)
        self.module_toggle_btn.setFixedHeight(28)
        self.module_toggle_btn.clicked.connect(self._on_module_switch_clicked)

        actions.addWidget(self.module_switch_label, 0, Qt.AlignLeft | Qt.AlignVCenter)
        actions.addWidget(self.module_toggle_btn, 0, Qt.AlignLeft | Qt.AlignVCenter)
        actions.addStretch(1)
        actions.addWidget(self.edit_btn)
        actions.addWidget(self.delete_btn)
        actions.addWidget(self.add_btn)
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

    def set_master_filter(self, jaw_ids, active: bool, refresh: bool = True):
        self._master_filter_ids = {self._norm_id(j) for j in (jaw_ids or []) if str(j).strip()}
        self._master_filter_active = bool(active) and bool(self._master_filter_ids)
        if refresh:
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
        self._on_type_filter_changed(self.jaw_type_filter.currentIndex())

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
        jaw_id_lbl.setMinimumWidth(0)
        jaw_id_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        diam_lbl = QLabel(jaw.get('clamping_diameter_text', '') or '')
        diam_lbl.setProperty('detailHeroTitle', True)
        diam_lbl.setWordWrap(True)
        diam_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        diam_lbl.setMinimumWidth(0)
        diam_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
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
            field_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
            field_frame.setMinimumWidth(0)
            fl = QVBoxLayout(field_frame)
            fl.setContentsMargins(6, 4, 6, 4)
            fl.setSpacing(4)
            klbl = QLabel(label_text)
            klbl.setProperty('detailFieldKey', True)
            klbl.setWordWrap(True)
            klbl.setMinimumWidth(0)
            klbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            vlbl = QLabel(value_text if value_text else '-')
            vlbl.setProperty('detailValue', True)
            vlbl.setProperty('detailFieldValue', True)
            vlbl.setWordWrap(True)
            vlbl.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            vlbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            vlbl.setMinimumWidth(0)
            vlbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            fl.addWidget(klbl)
            fl.addWidget(vlbl)
            return field_frame

        def build_used_in_works_field(value_text: str):
            field_frame = QFrame()
            field_frame.setProperty('detailField', True)
            field_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
            field_frame.setMinimumWidth(0)
            fl = QVBoxLayout(field_frame)
            fl.setContentsMargins(6, 4, 6, 4)
            fl.setSpacing(4)

            klbl = QLabel(self._t('jaw_library.field.used_in_works', 'Used in works:'))
            klbl.setProperty('detailFieldKey', True)
            klbl.setWordWrap(True)
            klbl.setMinimumWidth(0)
            klbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            fl.addWidget(klbl)

            works = self._split_used_in_works(value_text)
            if not works:
                empty = QLabel('-')
                empty.setProperty('detailValue', True)
                empty.setProperty('detailFieldValue', True)
                empty.setWordWrap(True)
                empty.setAlignment(Qt.AlignLeft | Qt.AlignTop)
                empty.setTextInteractionFlags(Qt.TextSelectableByMouse)
                empty.setMinimumWidth(0)
                empty.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
                fl.addWidget(empty)
                return field_frame

            for idx, work in enumerate(works):
                value = QLabel(work)
                value.setProperty('detailValue', True)
                value.setProperty('detailFieldValue', True)
                value.setWordWrap(True)
                value.setAlignment(Qt.AlignLeft | Qt.AlignTop)
                value.setTextInteractionFlags(Qt.TextSelectableByMouse)
                value.setMinimumWidth(0)
                value.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
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
        info.setColumnStretch(0, 1)
        info.setColumnStretch(1, 1)
        info.setColumnStretch(2, 1)
        info.setColumnStretch(3, 1)
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
            notes_field.setMinimumWidth(0)
            notes_field.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
            nl = QVBoxLayout(notes_field)
            nl.setContentsMargins(6, 4, 6, 4)
            nl.setSpacing(4)
            nk = QLabel(self._t('jaw_library.field.notes', 'Notes'))
            nk.setProperty('detailFieldKey', True)
            nk.setWordWrap(True)
            nk.setMinimumWidth(0)
            nk.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            nv = QLabel(notes_text)
            nv.setProperty('detailValue', True)
            nv.setProperty('detailFieldValue', True)
            nv.setWordWrap(True)
            nv.setTextInteractionFlags(Qt.TextSelectableByMouse)
            nv.setMinimumWidth(0)
            nv.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
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

    def _update_row_type_visibility(self, _show: bool):
        """Delegate rows are painted directly; a viewport repaint is sufficient."""
        self.jaw_list.viewport().update()

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
        if not hasattr(self, 'jaw_list'):
            return
        type_filter = self.jaw_type_filter.currentData() if hasattr(self, 'jaw_type_filter') else 'all'
        jaws = self.jaw_service.list_jaws(self.search.text(), self.current_view_mode, type_filter)
        if self._master_filter_active:
            jaws = [jaw for jaw in jaws if self._norm_id(jaw.get('jaw_id', '')) in self._master_filter_ids]
        self.jaw_list.setUpdatesEnabled(False)
        self._jaw_model.clear()
        items = []
        for jaw in jaws:
            item = QStandardItem()
            item.setData(jaw.get('jaw_id', ''), ROLE_JAW_ID)
            item.setData(jaw, ROLE_JAW_DATA)
            item.setData(jaw_icon_for_row(jaw), ROLE_JAW_ICON)
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            items.append(item)
        if items:
            self._jaw_model.invisibleRootItem().appendRows(items)
        self.jaw_list.setUpdatesEnabled(True)
        found = False
        if self.current_jaw_id:
            for row in range(self._jaw_model.rowCount()):
                idx = self._jaw_model.index(row, 0)
                if idx.data(ROLE_JAW_ID) == self.current_jaw_id:
                    self.jaw_list.setCurrentIndex(idx)
                    self.jaw_list.scrollTo(idx)
                    found = True
                    break
        if self.current_jaw_id and not found:
            self.current_jaw_id = None
            self.jaw_list.setCurrentIndex(QModelIndex())
            if not self._details_hidden:
                self.populate_details(None)
        self.jaw_list.doItemsLayout()
        self.jaw_list.viewport().update()

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
        self._update_row_type_visibility(False)

    def hide_details(self):
        self._details_hidden = True
        if self.detail_container.isVisible():
            self._last_splitter_sizes = self.splitter.sizes()
        self.detail_container.hide()
        self.detail_header_container.hide()
        self.splitter.setSizes([1, 0])
        self._update_row_type_visibility(True)

    def _on_current_changed(self, current: QModelIndex, previous: QModelIndex):
        _ = previous
        if not current.isValid():
            self.current_jaw_id = None
            self.populate_details(None)
            return

        self.current_jaw_id = current.data(ROLE_JAW_ID)
        if not self._details_hidden:
            jaw = self.jaw_service.get_jaw(self.current_jaw_id)
            self.populate_details(jaw)

    def _on_double_clicked(self, index: QModelIndex):
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

    def apply_localization(self, translate: Callable[[str, str | None], str] | None = None):
        if translate is not None:
            self._translate = translate
        if hasattr(self, '_jaw_delegate'):
            self._jaw_delegate.set_translate(self._t)
            self.jaw_list.viewport().update()
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

