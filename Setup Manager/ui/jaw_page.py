import numpy as np

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPalette, QPixmap, QTransform
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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
from ui.stl_preview import StlPreviewWidget
from ui.widgets.common import AutoShrinkLabel, BorderOnlyComboItemDelegate, add_shadow


class JawRowWidget(QFrame):
    def __init__(self, jaw: dict, parent=None):
        super().__init__(parent)
        self.jaw = jaw
        self.setProperty('toolListCard', True)
        self.setProperty('selected', False)
        self._val_labels: list[QLabel] = []
        self._head_labels: list[QLabel] = []
        self._col_layouts: list[QVBoxLayout] = []
        self._build_ui()

    def _card_columns(self):
        return [
            ('jaw_id', 'Jaw ID', self.jaw.get('jaw_id', ''), 180),
            ('jaw_type', 'Jaw type', self.jaw.get('jaw_type', ''), 210),
            ('diameter', 'Clamping diameter', self.jaw.get('clamping_diameter_text', '') or '—', 190),
            ('length', 'Clamping length', self.jaw.get('clamping_length', '') or '—', 180),
        ]

    def _value(self, text: str) -> QLabel:
        lbl = AutoShrinkLabel(text)
        lbl.setProperty('toolCardValue', True)
        lbl.setAlignment(Qt.AlignCenter)
        return lbl

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(10)

        icon_label = QLabel()
        icon_path = TOOL_ICONS_DIR / _DEFAULT_JAW_ICON
        icon_target_size = QSize(48, 48)
        spindle_side = (self.jaw.get('spindle_side') or '').strip()
        if icon_path.exists():
            pixmap = _load_transparent_icon(icon_path)
            if spindle_side in ('Sub spindle', 'SP2'):
                pixmap = pixmap.transformed(QTransform().scale(-1, 1), Qt.SmoothTransformation)
            pixmap = pixmap.scaled(icon_target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            pixmap = QIcon(str(TOOL_ICONS_DIR / 'jaw_icon.png')).pixmap(icon_target_size)
        icon_label.setPixmap(pixmap)
        icon_label.setFixedSize(56, 56)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet('background-color: transparent;')
        layout.addWidget(icon_label, 0, Qt.AlignVCenter)

        for _key, title, value, weight in self._card_columns():
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(1)
            self._col_layouts.append(col)

            head = QLabel(title)
            head.setProperty('toolCardHeader', True)
            head.setAlignment(Qt.AlignCenter)
            head.setWordWrap(True)
            head.setMinimumHeight(20)

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
            lay.setContentsMargins(7, 4, 7, 4)
            lay.setSpacing(7)
            v_size, h_size, col_spacing = 11.5, 8.6, 1
        else:
            lay.setContentsMargins(10, 4, 10, 4)
            lay.setSpacing(10)
            v_size, h_size, col_spacing = 12.8, 9.4, 1
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


class JawPage(QWidget):
    NAV_MODES = [
        ('All Jaws', 'all'),
        ('SP1', 'main'),
        ('SP2', 'sub'),
        ('Soft Jaws', 'soft'),
        ('Hard / Spiked / Special', 'hard_group'),
    ]

    def __init__(self, jaw_service, parent=None, show_sidebar: bool = True):
        super().__init__(parent)
        self.jaw_service = jaw_service
        self.show_sidebar = show_sidebar
        self.current_jaw_id = None
        self.current_view_mode = 'all'
        self._details_hidden = True
        self._last_splitter_sizes = None
        self._module_switch_callback = None
        self._build_ui()
        self.refresh_list()

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

        self.toolbar_title_label = QLabel('JAWS')
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
        self.search.setPlaceholderText('Search jaw ID, type, spindle, diameter, work, washer or notes')
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
        self.detail_section_label = QLabel('Jaw details')
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
        self.jaw_type_filter.addItems(['All', 'Soft Jaws', 'Spike/Hard Jaws', 'Special Jaws'])
        self.jaw_type_filter.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.jaw_type_filter.setMinimumWidth(60)
        self.jaw_type_filter.currentTextChanged.connect(self._on_type_filter_changed)
        add_shadow(self.jaw_type_filter)
        self._apply_combobox_popup_style(self.jaw_type_filter)
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
            self.sidebar.setFixedWidth(220)
            side_layout = QVBoxLayout(self.sidebar)
            side_layout.setContentsMargins(10, 12, 10, 12)
            side_layout.setSpacing(6)

            side_title = QLabel('Jaw Views')
            side_title.setProperty('detailSectionTitle', True)
            side_layout.addWidget(side_title)

            for title, mode in self.NAV_MODES:
                btn = QPushButton(title)
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

        self.jaw_list = QListWidget()
        self.jaw_list.setObjectName('toolCatalog')
        self.jaw_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.jaw_list.setSpacing(4)
        self.jaw_list.installEventFilter(self)
        self.jaw_list.viewport().installEventFilter(self)
        self.jaw_list.currentItemChanged.connect(self.on_current_item_changed)
        self.jaw_list.itemDoubleClicked.connect(self.on_item_double_clicked)
        list_layout.addWidget(self.jaw_list, 1)

        self.splitter.addWidget(list_card)

        self.detail_container = QWidget()
        self.detail_container.setMinimumWidth(390)
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

        self.edit_btn = QPushButton('EDIT JAW')
        self.delete_btn = QPushButton('DELETE JAW')
        self.add_btn = QPushButton('ADD JAW')
        for btn in [self.edit_btn, self.delete_btn, self.add_btn]:
            btn.setProperty('panelActionButton', True)
        self.delete_btn.setProperty('dangerAction', True)
        self.add_btn.setProperty('primaryAction', True)

        self.edit_btn.clicked.connect(self.edit_jaw)
        self.delete_btn.clicked.connect(self.delete_jaw)
        self.add_btn.clicked.connect(self.add_jaw)

        self.module_switch_label = QLabel('Switch to')
        self.module_switch_label.setProperty('pageSubtitle', True)
        self.module_toggle_btn = QPushButton('TOOLS')
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
        self.module_toggle_btn.setText(target_text)
        self.module_toggle_btn.setToolTip(f'Switch to {target_text} module')

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

    def _rebuild_filter_row(self):
        while self.filter_layout.count():
            item = self.filter_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        self.filter_layout.addWidget(self.toolbar_title_label)
        self.filter_layout.addSpacing(14)
        self.filter_layout.addWidget(self.search_toggle)
        self.filter_layout.addWidget(self.toggle_details_btn)
        if self.search.isVisible():
            self.filter_layout.addWidget(self.search, 1)
        self.filter_layout.addWidget(self.filter_icon)
        self.filter_layout.addWidget(self.jaw_type_filter)
        self.filter_layout.addStretch(1)
        self.filter_layout.addWidget(self.detail_header_container)

    def _apply_combobox_popup_style(self, combo: QComboBox):
        view = combo.view()
        view.setMouseTracking(True)
        view.viewport().setMouseTracking(True)
        view.setItemDelegate(BorderOnlyComboItemDelegate(view))
        pal = view.palette()
        pal.setColor(QPalette.Base, QColor('#FCFCFC'))
        pal.setColor(QPalette.Text, QColor('#000000'))
        pal.setColor(QPalette.Highlight, QColor('#FCFCFC'))
        pal.setColor(QPalette.HighlightedText, QColor('#000000'))
        view.setPalette(pal)
        view.setStyleSheet(
            "QListView { background: #FCFCFC; color: #000000;"
            " selection-background-color: #FCFCFC; selection-color: #000000; outline: none; }"
            "QListView::item { background: #FCFCFC; color: #000000;"
            " border: none; padding: 8px 12px; }"
        )

    def _on_type_filter_changed(self, text: str):
        active = text != 'All'
        icon_name = 'filter_off.svg' if active else 'filter_arrow_right.svg'
        self.filter_icon.setIcon(QIcon(str(TOOL_ICONS_DIR / icon_name)))
        self.refresh_list()

    def _clear_type_filter(self):
        self.jaw_type_filter.setCurrentText('All')

    def eventFilter(self, obj, event):
        if obj is getattr(self, 'jaw_type_filter', None) or (
                getattr(self, 'jaw_type_filter', None) and obj is self.jaw_type_filter.view()):
            if getattr(self, '_suppress_combo', False) and event.type() in (QEvent.Show, QEvent.ShowToParent):
                return True
            if event.type() == QEvent.Enter:
                obj.setProperty('hovered', True)
                obj.style().polish(obj)
            elif event.type() == QEvent.Leave:
                obj.setProperty('hovered', False)
                obj.style().polish(obj)
        if obj in (getattr(self, 'jaw_list', None),
                   getattr(self, 'jaw_list', None) and self.jaw_list.viewport()):
            if event.type() == QEvent.MouseButtonPress and self.jaw_list.itemAt(event.pos()) is None:
                self._clear_selection()
        return super().eventFilter(obj, event)

    def _clear_selection(self):
        current = getattr(self, 'jaw_list', None) and self.jaw_list.currentItem()
        if current:
            prev_widget = self.jaw_list.itemWidget(current)
            if prev_widget is not None:
                prev_widget.setProperty('selected', False)
                self._refresh_row_style(prev_widget)
        if hasattr(self, 'jaw_list'):
            self.jaw_list.setCurrentRow(-1)
            self.jaw_list.clearSelection()
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
            title = QLabel('Jaw details')
            title.setProperty('detailSectionTitle', True)
            hint = QLabel('Select a jaw to view details.')
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
        badge = QLabel(jaw.get('jaw_type', ''))
        badge.setProperty('toolBadge', True)
        badge_row.addWidget(badge, 0, Qt.AlignLeft)
        badge_row.addStretch(1)
        h_layout.addLayout(title_row)
        h_layout.addLayout(badge_row)
        layout.addWidget(header)

        # detailField grid — same card-box style as Tool Library
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
            vlbl = QLabel(value_text if value_text else '—')
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

            klbl = QLabel('Used in works:')
            klbl.setProperty('detailFieldKey', True)
            klbl.setWordWrap(False)
            fl.addWidget(klbl)

            works = self._split_used_in_works(value_text)
            if not works:
                empty = QLabel('—')
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
        spindle_side_text = (jaw.get('spindle_side', '') or '').strip()
        if spindle_side_text == 'Main spindle':
            spindle_side_text = 'SP1'
        elif spindle_side_text == 'Sub spindle':
            spindle_side_text = 'SP2'

        pairs = [
            ('Jaw ID',            jaw.get('jaw_id', '')),
            ('Spindle side',      spindle_side_text),
            ('Clamping diameter', jaw.get('clamping_diameter_text', '')),
            ('Clamping length',   jaw.get('clamping_length', '')),
            ('Turning ring',      jaw.get('turning_washer', '')),
            ('Last modified',     jaw.get('last_modified', '')),
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
            nk = QLabel('Notes')
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

        # Preview panel — diagramPanel wrapper matches Tool Library style
        preview_card = QFrame()
        preview_card.setProperty('subCard', True)
        p_layout = QVBoxLayout(preview_card)
        p_layout.setContentsMargins(12, 12, 12, 12)
        p_layout.setSpacing(10)
        p_title = QLabel('Preview')
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
            viewer.load_stl(stl_path, label=jaw.get('jaw_id', 'Jaw'))
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
            txt = QLabel('No 3D model assigned.')
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

    def refresh_list(self):
        type_filter = self.jaw_type_filter.currentText() if hasattr(self, 'jaw_type_filter') else 'All'
        jaws = self.jaw_service.list_jaws(self.search.text(), self.current_view_mode, type_filter)
        self.jaw_list.clear()

        for jaw in jaws:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, jaw.get('jaw_id', ''))
            widget = JawRowWidget(jaw)
            self.jaw_list.addItem(item)
            self.jaw_list.setItemWidget(item, widget)
            widget.adjustSize()
            widget_size = widget.sizeHint()
            spacing = max(0, self.jaw_list.spacing())
            min_h = 72
            final_h = max(widget_size.height(), min_h) + spacing
            item.setSizeHint(QSize(widget_size.width() or 0, final_h))

        if self.current_jaw_id:
            for idx in range(self.jaw_list.count()):
                item = self.jaw_list.item(idx)
                if item.data(Qt.UserRole) == self.current_jaw_id:
                    self.jaw_list.setCurrentItem(item)
                    break

    def toggle_details(self):
        if self._details_hidden:
            if not self.current_jaw_id:
                QMessageBox.information(self, 'Show details', 'Select a jaw first.')
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

    def hide_details(self):
        self._details_hidden = True
        if self.detail_container.isVisible():
            self._last_splitter_sizes = self.splitter.sizes()
        self.detail_container.hide()
        self.detail_header_container.hide()
        self.splitter.setSizes([1, 0])

    def on_current_item_changed(self, current, previous):
        if previous is not None:
            prev_widget = self.jaw_list.itemWidget(previous)
            if prev_widget is not None:
                prev_widget.setProperty('selected', False)
                self._refresh_row_style(prev_widget)

        if current is None:
            self.current_jaw_id = None
            self.populate_details(None)
            return

        self.current_jaw_id = current.data(Qt.UserRole)
        current_widget = self.jaw_list.itemWidget(current)
        if current_widget is not None:
            current_widget.setProperty('selected', True)
            self._refresh_row_style(current_widget)

        if not self._details_hidden:
            jaw = self.jaw_service.get_jaw(self.current_jaw_id)
            self.populate_details(jaw)

    def on_item_double_clicked(self, item):
        self.current_jaw_id = item.data(Qt.UserRole)
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
            QMessageBox.warning(self, 'Invalid data', str(exc))

    def add_jaw(self):
        dlg = AddEditJawDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self._save_from_dialog(dlg)

    def edit_jaw(self):
        if not self.current_jaw_id:
            QMessageBox.information(self, 'Edit jaw', 'Select a jaw first.')
            return
        jaw = self.jaw_service.get_jaw(self.current_jaw_id)
        dlg = AddEditJawDialog(self, jaw=jaw)
        if dlg.exec() == QDialog.Accepted:
            self._save_from_dialog(dlg)

    def delete_jaw(self):
        if not self.current_jaw_id:
            QMessageBox.information(self, 'Delete jaw', 'Select a jaw first.')
            return
        answer = QMessageBox.question(self, 'Delete jaw', f'Delete jaw {self.current_jaw_id}?')
        if answer != QMessageBox.Yes:
            return
        self.jaw_service.delete_jaw(self.current_jaw_id)
        self.current_jaw_id = None
        self.refresh_list()
        self.populate_details(None)
