
import json
from PySide6.QtCore import Qt, QSize, QUrl, QTimer, QModelIndex, QItemSelectionModel
from PySide6.QtGui import QIcon, QDesktopServices, QFontMetrics, QKeySequence, QShortcut, QStandardItemModel, QStandardItem, QColor, QPainter, QPixmap, QTransform, QCursor
# import QtSvg so that SVG image support is initialized early
import PySide6.QtSvg  # noqa: F401
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractItemView, QApplication, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QDialogButtonBox, QLabel, QLineEdit, QListView, QMessageBox, QPushButton,
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
from ui.tool_catalog_delegate import (
    ToolCatalogDelegate, tool_icon_for_type,
    ROLE_TOOL_ID, ROLE_TOOL_DATA, ROLE_TOOL_ICON, ROLE_TOOL_UID,
)
from ui.widgets.common import add_shadow, apply_shared_dropdown_style, repolish_widget
from shared.editor_helpers import apply_secondary_button_theme, create_dialog_buttons, setup_editor_dialog

# the STL preview widget may live in a separate module; import lazily so the
# rest of the application still runs if the real implementation is missing.
try:
    from ui.stl_preview import StlPreviewWidget
except ImportError:  # pragma: no cover - safe fallback
    StlPreviewWidget = None


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
        """Called when the detail panel opens/closes.
        With the delegate-based list, we just need to trigger a repaint.
        """
        self.tool_list.viewport().update()

    def _refresh_row_style(self, widget):
        """No-op — delegate rows don't have child widgets to repolish."""
        pass

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

        # search toggle button - use image assets instead of a unicode glyph
        self.search_toggle = QToolButton()
        # PNG avoids occasional SVG clipping on some Qt/Windows render paths.
        self.search_icon = QIcon(str(TOOL_ICONS_DIR / 'search_icon.png'))
        self.close_icon = QIcon(str(TOOL_ICONS_DIR / 'close_icon.svg'))
        self.search_toggle.setIcon(self.search_icon)
        # slightly larger than before so the glass is visible
        # bump default icon size up a bit
        self.search_toggle.setIconSize(QSize(24, 24))
        self.search_toggle.setCheckable(True)
        self.search_toggle.setAutoRaise(True)
        self.search_toggle.setProperty('topBarIconButton', True)
        # larger overall to give padding around the graphic
        self.search_toggle.setFixedSize(34, 34)
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

        self.tool_list = QListView()
        self.tool_list.setObjectName('toolCatalog')
        self.tool_list.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.tool_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tool_list.setSelectionMode(QListView.SingleSelection)
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
        button_layout.addWidget(self.add_btn)
        button_layout.addWidget(self.edit_btn)
        button_layout.addWidget(self.delete_btn)
        button_layout.addWidget(self.copy_btn)
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
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
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
                if not self.tool_list.indexAt(event.pos()).isValid():
                    self._clear_selection()
        return super().eventFilter(obj, event)

    def _clear_selection(self):
        """Internal helper to clear row selection and reset details."""
        details_were_open = not self._details_hidden
        if hasattr(self, 'tool_list'):
            self.tool_list.selectionModel().clearSelection()
            self.tool_list.setCurrentIndex(QModelIndex())
        self.current_tool_id = None
        self.current_tool_uid = None
        self.populate_details(None)
        if details_were_open:
            self.hide_details()
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

    def _on_current_changed(self, current: QModelIndex, previous: QModelIndex):
        if not current.isValid():
            self.current_tool_id = None
            self.current_tool_uid = None
            self.populate_details(None)
            if self.preview_window_btn.isChecked():
                self._close_detached_preview()
            return
        self.current_tool_id = current.data(ROLE_TOOL_ID)
        self.current_tool_uid = current.data(ROLE_TOOL_UID)
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
            field_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
            field_frame.setMinimumWidth(0)
            flayout = QVBoxLayout(field_frame)
            flayout.setContentsMargins(6, 4, 6, 4)
            flayout.setSpacing(4)
            key_lbl = self._detail_key_label(label_text)
            key_lbl.setWordWrap(True)
            value_lbl = self._value_label(value_text)
            value_lbl.setProperty('detailFieldValue', True)
            flayout.addWidget(key_lbl)
            flayout.addWidget(value_lbl)
            return field_frame

        raw_cutting_type = tool.get('cutting_type', 'Insert')

        # Build the information grid.
        # Row 0: Geom X (left half) | Geom Z (right half)
        # Row 1: Radius (left half) | Nose R / Corner R (right half)
        # Row 2+: type-specific fields and notes.
        info = QGridLayout()
        info.setHorizontalSpacing(14)
        info.setVerticalSpacing(8)
        info.setColumnStretch(0, 1)
        info.setColumnStretch(1, 1)
        info.setColumnStretch(2, 1)
        info.setColumnStretch(3, 1)

        info.addWidget(build_field(self._t('tool_library.field.geom_x', 'Geom X'), str(tool.get('geom_x', ''))), 0, 0, 1, 2, Qt.AlignTop)
        info.addWidget(build_field(self._t('tool_library.field.geom_z', 'Geom Z'), str(tool.get('geom_z', ''))), 0, 2, 1, 2, Qt.AlignTop)
        info.addWidget(build_field(self._t('tool_library.field.radius', 'Radius'), str(tool.get('radius', ''))), 1, 0, 1, 2, Qt.AlignTop)
        info.addWidget(build_field(self._t('tool_library.field.nose_corner_radius', 'Nose R / Corner R'), str(tool.get('nose_corner_radius', ''))), 1, 2, 1, 2, Qt.AlignTop)

        full_row = 2
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
        lbl.setMinimumWidth(0)
        lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        return lbl
    
    def _detail_key_label(self, text):
        lbl = QLabel(text)
        lbl.setProperty('detailFieldKey', True)
        lbl.setWordWrap(True)
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
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        row = 0

        def _component_key(item: dict, fallback_idx: int) -> str:
            explicit = (item.get('component_key') or '').strip()
            if explicit:
                return explicit
            role = (item.get('role') or 'component').strip().lower()
            code = (item.get('code') or '').strip()
            if code:
                return f"{role}:{code}"
            return f"{role}:idx:{fallback_idx}"

        def _wrap_title(text: str) -> str:
            raw = (text or '').strip()
            if len(raw) <= 18:
                return raw
            words = raw.split()
            if len(words) <= 1:
                return raw
            line1 = ''
            line2 = ''
            for word in words:
                candidate = (line1 + ' ' + word).strip()
                if not line1 or len(candidate) <= 18:
                    line1 = candidate
                else:
                    line2 = (line2 + ' ' + word).strip()
            return f"{line1}\n{line2}" if line2 else line1

        component_items = tool.get('component_items', [])
        if isinstance(component_items, str):
            try:
                component_items = json.loads(component_items or '[]')
            except Exception:
                component_items = []

        normalized = []
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
            # Legacy fallback for rows without component_items.
            raw_cutting_name = tool.get('cutting_type', '')
            cutting_name = self._localized_cutting_type(raw_cutting_name) if raw_cutting_name else self._t('tool_library.field.cutting_part', 'Cutting part')
            legacy_candidates = [
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
            normalized.extend([item for item in legacy_candidates if (item.get('code') or '').strip()])

        normalized.sort(key=lambda entry: int(entry.get('order', 0)))

        spare_index = {}
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
            spare_index.setdefault(part_key, []).append(part)

        last_group = None
        for idx, item in enumerate(normalized):
            group = (item.get('group') or '').strip()
            if group != last_group:
                last_group = group
                if group:
                    group_label = QLabel(group)
                    group_label.setProperty('detailGroupHeading', True)
                    group_label.setStyleSheet(
                        'background: transparent;'
                        'font-weight: 600; font-size: 11px; color: #5a6a7a;'
                        'border-bottom: 1px solid #d0d8e0; padding: 4px 0 2px 0;'
                        'margin-top: 6px;'
                    )
                    grid.addWidget(group_label, row, 0, 1, 2)
                    row += 1

            display_name = item.get('label', self._t('tool_library.field.part', 'Part'))
            wrapped_name = _wrap_title(display_name)

            component_key = _component_key(item, idx)
            linked_spares = spare_index.get(component_key, [])

            btn = QPushButton(wrapped_name)
            btn.setProperty('assemblyPart', True)
            btn.setProperty('panelActionButton', True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip((item.get('link') or '').strip() or self._t('tool_library.part.no_link', 'No link set for: {name}', name=display_name))
            btn.setMinimumWidth(100)
            fm = QFontMetrics(btn.font())
            widest_line = max([fm.horizontalAdvance(line) for line in wrapped_name.split('\n')] or [100])
            btn.setMaximumWidth(max(120, min(260, widest_line + 36)))
            btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            btn.clicked.connect(lambda _=False, p=item: self.part_clicked(p))

            grid.addWidget(btn, row, 0)

            # Code label + optional arrow indicator for spare parts
            code_row = QHBoxLayout()
            code_row.setContentsMargins(0, 0, 0, 0)
            code_row.setSpacing(6)
            code_lbl = QLabel(item.get('code', ''))
            code_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            code_style_default = (
                'background: transparent; border: none; color: #22303c; '
                'font-size: 12pt; font-weight: 500; padding: 0px;'
            )
            code_style_hover = (
                'background: transparent; border: none; color: #1f5f9a; '
                'font-size: 12pt; font-weight: 600; padding: 0px;'
            )
            code_lbl.setStyleSheet(code_style_default)
            code_row.addWidget(code_lbl, 1)

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
                code_row.addWidget(arrow_lbl, 0)
                # Make the whole code area clickable to toggle spares
                code_lbl.setCursor(Qt.PointingHandCursor)

            code_widget = QWidget()
            code_widget.setStyleSheet('background: transparent; border: none;')
            code_widget.setLayout(code_row)
            grid.addWidget(code_widget, row, 1)
            row += 1

            if linked_spares:
                spare_host = QFrame()
                spare_host.setStyleSheet(
                    'QFrame { background: #f8fbfd; border: 1px solid #d0d8e0; '
                    'border-radius: 4px; padding: 0px; margin: 0px; }'
                )
                spare_host_layout = QVBoxLayout(spare_host)
                spare_host_layout.setContentsMargins(10, 8, 10, 8)
                spare_host_layout.setSpacing(4)
                spare_host.setVisible(False)

                SPARE_BTN_WIDTH = 150

                for spare in linked_spares:
                    spare_row_layout = QHBoxLayout()
                    spare_row_layout.setContentsMargins(0, 0, 0, 0)
                    spare_row_layout.setSpacing(8)

                    spare_name = (spare.get('name') or self._t('tool_library.field.part', 'Part')).strip()
                    spare_code_lbl = self._value_label((spare.get('code') or '').strip())
                    spare_code_lbl.setStyleSheet(
                        'background: transparent; border: none; font-size: 10pt; color: #5a6a7a;'
                    )

                    spare_btn = QPushButton(_wrap_title(spare_name))
                    spare_btn.setProperty('panelActionButton', True)
                    spare_btn.setCursor(Qt.PointingHandCursor)
                    spare_btn.setToolTip((spare.get('link') or '').strip() or self._t('tool_library.part.no_link', 'No link set for: {name}', name=spare_name))
                    spare_btn.setStyleSheet('font-size: 9pt;')
                    spare_btn.setFixedWidth(SPARE_BTN_WIDTH)
                    spare_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
                    spare_btn.clicked.connect(lambda _=False, p=spare: self.part_clicked(p))

                    spare_row_layout.addWidget(spare_btn, 0)
                    spare_row_layout.addWidget(spare_code_lbl, 1)
                    spare_host_layout.addLayout(spare_row_layout)

                def _set_toggle_hover(hovered: bool, label=code_lbl):
                    label.setStyleSheet(code_style_hover if hovered else code_style_default)

                def _cursor_over_toggle(widget=code_widget):
                    if not widget.isVisible():
                        return False
                    return widget.rect().contains(widget.mapFromGlobal(QCursor.pos()))

                def _toggle_spares(
                    _e,
                    host=spare_host,
                    arrow=arrow_lbl,
                    up=arrow_up,
                    left=arrow_left,
                    panel=frame,
                    panel_grid=grid,
                    set_hover=_set_toggle_hover,
                    cursor_over=_cursor_over_toggle,
                ):
                    self._component_toggle_hover_suppressed = True
                    set_hover(False)
                    visible = not host.isVisible()
                    host.setVisible(visible)
                    arrow.setPixmap(up if visible else left)
                    panel_grid.activate()
                    panel.updateGeometry()
                    panel.update()

                    def _restore_hover(owner=self, apply_hover=set_hover, is_cursor_over=cursor_over):
                        owner._component_toggle_hover_suppressed = False
                        apply_hover(is_cursor_over())

                    QTimer.singleShot(90, _restore_hover)

                def _hover_enter(_e, set_hover=_set_toggle_hover):
                    if getattr(self, '_component_toggle_hover_suppressed', False):
                        return
                    set_hover(True)

                def _hover_leave(_e, set_hover=_set_toggle_hover):
                    if getattr(self, '_component_toggle_hover_suppressed', False):
                        return
                    set_hover(False)

                code_lbl.mousePressEvent = _toggle_spares
                arrow_lbl.mousePressEvent = _toggle_spares
                code_lbl.enterEvent = _hover_enter
                code_lbl.leaveEvent = _hover_leave
                arrow_lbl.enterEvent = _hover_enter
                arrow_lbl.leaveEvent = _hover_leave

                grid.addWidget(spare_host, row, 0, 1, 2)
                row += 1

        if row == 0:
            grid.addWidget(self._value_label('-'), row, 0, 1, 2)
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
                    return

            saved_uid = self.tool_service.save_tool(data, allow_duplicate=True)
            saved_tool = self.tool_service.get_tool_by_uid(saved_uid)
            self.current_tool_uid = saved_uid
            self.current_tool_id = (saved_tool or {}).get('id', data['id'])
            self.refresh_list()
            self.populate_details(saved_tool)
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
        tool = self._get_selected_tool()
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
        new_desc, _ = self._prompt_text(
            self._t('tool_library.action.copy_tool_title', 'Copy tool'),
            self._t('tool_library.prompt.new_description_optional', 'New description (optional):'),
        )
        try:
            if self.current_tool_uid is not None:
                copied = self.tool_service.copy_tool_by_uid(self.current_tool_uid, new_id, new_desc)
            else:
                copied = self.tool_service.copy_tool(self.current_tool_id, new_id, new_desc)
            self.current_tool_uid = copied.get('uid') if isinstance(copied, dict) else None
            self.current_tool_id = (copied.get('id') if isinstance(copied, dict) else '') or new_id.strip()
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

